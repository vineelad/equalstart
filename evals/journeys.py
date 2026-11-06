"""Synthetic end-to-end journeys and one-role-at-a-time ablations.

Run: python -m evals.journeys --live --max-cost 1
Sources are controlled fixtures, not real program facts or an independent test set.
"""
import argparse
import csv
import hashlib
import html
import json
from datetime import date, datetime, timezone
from time import perf_counter

from equalstart.agents import PROMPT_VERSION
from equalstart.catalog import ROOT
from equalstart.providers import Fireworks
from equalstart.schema import Claim, Opportunity, Profile, Rule
from equalstart.storage import Store
from equalstart.workflow import run_matching, application_tasks
from evals.phase2 import Phase2Baseline

NOW = datetime(2026,11,3,3,tzinfo=timezone.utc)


def opportunity(rid, title="Environmental summer research", summary="Undergraduate environmental summer research with funding", **updates):
    value=dict(id=rid,title=title,provider="Synthetic evaluation provider",category="Research",summary=summary,
               location="USA fixture",tags=["Environment"],award="$2,000 stipend",housing="Provided",
               travel="Supported; timing unknown",fee="None stated in fixture",upfront="Confirmed none",
               deadline_date=date(2027,1,31),cycle="2027",cycle_status="Open",official_url=f"https://example.edu/{rid}",
               claims=[Claim(id=f"{rid}-funding",topic="funding",text="For 2027, travel is prepaid and selected students receive a $2,000 stipend.",url=f"https://example.edu/{rid}",checked=date(2026,11,2))],
               materials=[],confirmations=[],rules=[])
    value.update(updates)
    return Opportunity(**value)


def fixture_cases():
    college=opportunity("four-year",rules=[Rule(field="institution_type",op="eq",value="Four-year",label="Four-year institution",claim_id="four-year-funding")])
    transfer=opportunity("transfer",title="Community college transfer tuition scholarship",summary="Tuition support for community college transfer",category="Scholarship",tags=["All fields","Transfer"])
    reimbursed=opportunity("reimbursed",upfront="Reimbursement barrier")
    prepaid=opportunity("prepaid")
    unknown=opportunity("citizen-only",rules=[Rule(field="citizenship",op="eq",value="US citizen",label="US citizenship",claim_id="citizen-only-funding")])
    disputed=opportunity("disputed")
    documented=opportunity("documented",housing="Allowance or arranged")
    poetry=opportunity("poetry",title="Poetry tuition award",summary="Tuition support for literary arts",tags=["Arts"],category="Scholarship")
    music=opportunity("music",title="Music tuition award",summary="Tuition support for performance",tags=["Arts"],category="Scholarship")
    nomination=opportunity("nomination",materials=["Submit the final nominated application", "Receive the required institutional nomination", "Contact the nominating representative"])
    cases=[
        {"id":"community-college","profile":Profile(goal="Community college transfer tuition scholarship",institution_type="Community college",citizenship="US citizen"),"records":[college,transfer],"expected":{"selected":"transfer","excluded":"four-year"}},
        {"id":"no-upfront-funds","profile":Profile(goal="Environmental summer research",citizenship="US citizen",no_upfront=True),"records":[reimbursed,prepaid],"expected":{"first":"prepaid"}},
        {"id":"missing-residency","profile":Profile(goal="Environmental summer research",citizenship=None),"records":[unknown],"expected":{"status":["citizen-only","Needs confirmation"]}},
        {"id":"known-restriction","profile":Profile(goal="Environmental summer research",citizenship="International student"),"records":[unknown],"expected":{"empty":True}},
        {"id":"conflicting-source","profile":Profile(goal="Environmental summer research",citizenship="US citizen",needs_housing=False),"records":[disputed,documented],"expected":{"first":"documented","contradicted":"disputed-funding"}},
        {"id":"no-relevant-match","profile":Profile(goal="Astronomy astrophysics research internship",discipline="STEM",citizenship="US citizen"),"records":[poetry,music],"expected":{"empty":True}},
        {"id":"nomination-plan","profile":Profile(goal="Environmental summer research",citizenship="US citizen"),"records":[nomination],"expected":{"plan_order":["material-2","material-1","material-0"]}},
    ]
    for case in cases:
        case["sources"]={str(record.official_url):"\n\n".join(claim.text for claim in record.claims) for record in case["records"]}
    conflict=next(case for case in cases if case["id"]=="conflicting-source")
    conflict["sources"][str(disputed.official_url)]="For the 2027 cycle, students must pay travel costs themselves before reimbursement. Travel is not prepaid; a $2,000 stipend is available."
    return cases


class FixtureSearch:
    def __init__(self,sources): self.sources=sources
    def search(self,*args): return []
    def fetch(self,url,hosts): return {"content":self.sources[url]}


class AblatedProvider:
    ready=True
    def __init__(self,provider,disabled):
        self.provider,self.disabled,self.calls=provider,disabled,0
        self.baseline=Phase2Baseline()
    def generate(self,role,*args):
        if self.provider is None or role in self.disabled:
            return self.baseline.generate(role,*args)
        self.calls+=1
        return self.provider.generate(role,*args)


def check(case,result,tasks):
    selected=result["selected_ids"]
    expected=case["expected"]
    checks={"known_rules_preserved":all(m.status!="Not eligible" and m.cycle_status!="Closed" for m in result["matches"] if m.opportunity_id in selected),
            "no_stage_fallback":not any(event.status=="Fallback" for event in result["events"])}
    if "selected" in expected: checks["relevant_selected"]=expected["selected"] in selected
    if "excluded" in expected: checks["restriction_excluded"]=expected["excluded"] not in selected
    if expected.get("empty"): checks["honest_empty_selection"]=not selected
    if "first" in expected: checks["appropriate_first"]=bool(selected) and selected[0]==expected["first"]
    if "status" in expected:
        rid,status=expected["status"]
        checks["unknown_preserved"]=next(m.status for m in result["matches"] if m.opportunity_id==rid)==status
    if "contradicted" in expected:
        checks["contradiction_recognized"]=any(f["claim_id"]==expected["contradicted"] and f["status"]=="Contradicted" for f in result.get("findings",[]))
    if "plan_order" in expected:
        actual=[task.id for task in tasks if task.id.startswith("material-")]
        checks["prerequisite_order"]=actual==expected["plan_order"]
    return checks


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live",action="store_true")
    parser.add_argument("--max-cost",type=float,default=1)
    args=parser.parse_args()
    if not 0<args.max_cost<=15: parser.error("Use a positive cap up to $15")
    store=Store()
    model=Fireworks(store) if args.live else None
    if model and not model.ready: parser.error("Model is not configured")
    before=store.spent()
    if model: model.cap=min(model.cap,before+args.max_cost)
    stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    out=ROOT/"docs"/"experiments"/("journeys-"+stamp)
    out.mkdir(parents=True,exist_ok=False)
    cases=fixture_cases()
    serialized=[{**case,"profile":case["profile"].model_dump(mode="json"),"records":[r.model_dump(mode="json") for r in case["records"]]} for case in cases]
    (out/"cases.json").write_text(json.dumps(serialized,indent=2),encoding="utf-8")
    metadata={"run_id":out.name,"prompt_version":PROMPT_VERSION,"live":args.live,"model":model.model if model else "local baseline",
              "dataset_fingerprint":hashlib.sha256(json.dumps(serialized,sort_keys=True).encode()).hexdigest(),
              "annotation":"AI-assisted synthetic development journeys with controlled source fixtures; not real student trials or independently reviewed labels.",
              "initial_ledger_usd":before,"started_utc":datetime.now(timezone.utc).isoformat()}
    metadata["source_fingerprint"]=hashlib.sha256("\n".join((ROOT/"equalstart"/name).read_text(encoding="utf-8") for name in ("agents.py","research.py","workflow.py","schema.py","providers.py","preparation.py")).encode()).hexdigest()
    metadata["model_config"]={"temperature":0,"reasoning_effort":"low","max_output_tokens":4096}
    metadata["cost_attribution"]="Provider request IDs; settled usage or retained reservation"
    variants={"full":set(),"local-baseline":set(("Discovery","Evidence","Fit","Planning")),
              **{f"without-{role.lower()}":{role} for role in ("Discovery","Evidence","Fit","Planning")}}
    rows=[]
    with (out/"journal.jsonl").open("w",encoding="utf-8") as journal:
        for name,disabled in variants.items():
            for case in cases:
                provider=AblatedProvider(model,disabled)
                started=perf_counter(); cost=model.cost() if model else 0
                row={"variant":name,"case_id":case["id"],"passed":False,"checks":{},"error_type":None}
                try:
                    result=run_matching(case["profile"],case["records"],provider,now=NOW,search=FixtureSearch(case["sources"]),allow_clarification=False)
                    tasks=[]
                    if "plan_order" in case["expected"]:
                        tasks,_=application_tasks(case["records"][0],provider,today=NOW.date())
                    row["checks"]=check(case,result,tasks)
                    row["passed"]=all(row["checks"].values())
                    row["selected_ids"]=result["selected_ids"]
                except Exception as error:
                    row["error_type"]=type(error).__name__
                row.update(model_calls=provider.calls,latency_ms=round((perf_counter()-started)*1000,2),estimated_cost_delta_usd=round(model.cost()-cost,9) if model else 0)
                rows.append(row)
                journal.write(json.dumps(row)+"\n"); journal.flush()
                (out/"results.json").write_text(json.dumps({"metadata":metadata,"results":rows},indent=2),encoding="utf-8")
            print(f"Completed {name}",flush=True)
    summaries=[{"variant":name,"passed":sum(row["passed"] for row in rows if row["variant"]==name),"total":len(cases),
                "model_calls":sum(row["model_calls"] for row in rows if row["variant"]==name),
                "cost":sum(row["estimated_cost_delta_usd"] for row in rows if row["variant"]==name)} for name in variants]
    metadata.update(finished_utc=datetime.now(timezone.utc).isoformat(),final_ledger_usd=store.spent(),estimated_cost_delta_usd=model.cost() if model else 0.0)
    (out/"metadata.json").write_text(json.dumps(metadata,indent=2),encoding="utf-8")
    (out/"results.json").write_text(json.dumps({"metadata":metadata,"summaries":summaries,"results":rows},indent=2),encoding="utf-8")
    report="Equal Start journey ablations\n\n"+metadata["annotation"]+"\nSame fixed cases for every variant. One run per case; no statistical significance claim.\n\n"+"\n".join(f"{s['variant']}: {s['passed']}/{s['total']} | {s['model_calls']} model calls | estimated ${s['cost']:.6f}" for s in summaries)+"\n\nA disabled role uses the documented simple local comparator. The all-local variant uses no model calls. Tool sources are controlled fixtures, so this does not evaluate live web retrieval. Inspect failures before interpreting differences.\n"
    (out/"REPORT.txt").write_text(report,encoding="utf-8")
    (out/"dashboard.html").write_text("<!doctype html><html lang='en'><meta charset='utf-8'><title>Journey ablations</title><style>body{font:16px/1.6 system-ui;max-width:1100px;margin:40px auto}pre{white-space:pre-wrap}</style><h1>Journey ablations</h1><pre>"+html.escape(report)+"</pre><pre>"+html.escape(json.dumps(rows,indent=2))+"</pre></html>",encoding="utf-8")
    print(json.dumps({"directory":str(out),"summaries":summaries,"estimated_cost_delta_usd":metadata["estimated_cost_delta_usd"]}))
    return int(args.live and not all(row["passed"] for row in rows if row["variant"]=="full"))


if __name__=="__main__":
    raise SystemExit(main())
