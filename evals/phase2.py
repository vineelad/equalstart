"""Evaluate Phase 2 tool decisions and grounded evidence alongside Fit and Planning.

Run with the project Python: -m evals.phase2 [--live] [--repeats 3] [--max-cost 1]
Labels are never sent to providers. Cases are synthetic development evidence.
"""
import argparse
import csv
import hashlib
import html
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

from equalstart.agents import PROMPT_VERSION, invoke_agent, SPECS, RESEARCH_INSTRUCTION, GROUNDED_INSTRUCTION
from equalstart.catalog import ROOT
from equalstart.providers import Fireworks
from equalstart.schema import ResearchAction, GroundedEvidenceOutput, GroundedFinding
from equalstart.storage import Store
from evals.runner import Baseline, CountedProvider, FIELDS, score, summarize

DATASET = ROOT / "evals" / "phase2_cases.json"


class Phase2Baseline(Baseline):
    def generate(self, role, instruction, context, schema):
        if role == "Discovery" and "research_state" in context:
            state = context["research_state"]
            if state.get("clarification_available") and "clarify" in state["available_actions"]:
                return ResearchAction(action="clarify")
            if "fetch" in state["available_actions"] and state["fetchable_ids"]:
                return ResearchAction(action="fetch", opportunity_id=state["fetchable_ids"][0])
            return ResearchAction(action="finish")
        if role == "Evidence" and "sources" in context:
            return GroundedEvidenceOutput(findings=[GroundedFinding(claim_id=c["id"], snapshot_id=next(s["id"] for s in context["sources"] if s["opportunity_id"]==c["opportunity_id"]), status="Not found", quote="") for c in context["claims"]])
        return super().generate(role, instruction, context, schema)


def grade(case, output):
    if case["variant"] == "research":
        passed = output.action == case["expected"]["action"]
        return {"action_accuracy": float(passed)}, passed
    if case["variant"] == "grounded":
        actual = {f.claim_id: f.status for f in output.findings}
        expected = case["expected"]["statuses"]
        passed = actual == expected
        return {"finding_accuracy": sum(actual.get(key)==value for key,value in expected.items())/len(expected)}, passed
    return score(case, getattr(output, FIELDS[case["agent"]]))


def evaluate_case(case, provider, mode, repeat, store=None):
    counted = CountedProvider(provider)
    started = perf_counter()
    before = provider.cost() if store else 0
    row = {"case_id":case["id"], "agent":case["agent"], "slice":case["slice"], "repeat":repeat, "mode":mode,
           "contract_valid":False, "task_pass":False, "output":None, "error_type":None, "metrics":{}}
    try:
        output = invoke_agent(case["agent"], counted, case["context"])
        row["output"] = output.model_dump()
        row["contract_valid"] = True
        row["metrics"], row["task_pass"] = grade(case, output)
    except Exception as error:
        row["error_type"] = type(error).__name__
    row.update(model_calls=counted.calls if mode=="live" else 0,
               latency_ms=round((perf_counter()-started)*1000,3),
               estimated_cost_delta_usd=round(provider.cost()-before,9) if store else 0)
    return row


def write_report(directory, metadata, rows):
    summaries = summarize(rows)
    (directory/"results.json").write_text(json.dumps({"metadata":metadata,"summaries":summaries,"results":rows},indent=2),encoding="utf-8")
    with (directory/"results.csv").open("w",newline="",encoding="utf-8") as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows({**row,"output":json.dumps(row["output"]),"metrics":json.dumps(row["metrics"])} for row in rows)
    lines=["Equal Start Phase 2 agent evaluation", f"Run: {metadata['run_id']}",f"Prompt: {PROMPT_VERSION}",
           "AI-assisted synthetic development cases, not independent held-out accuracy.",
           "Discovery/Evidence cover new tool/grounding contracts; Fit/Planning reuse existing regression scenarios.",
           "Live gates per role: 100% contract validity and at least 90% task-case passes.",""]
    for summary in summaries:
        lines.append(f"{summary['agent']} | {summary['mode']} | {summary['task_passes']}/{summary['evaluations']} | contract {summary['contract_rate']:.1%} | gate {'PASS' if summary['release_gate'] else 'FAIL'}")
    lines += ["", "Failures:"] + [f"{row['case_id']} {row['mode']} repeat {row['repeat']}: {row['error_type'] or 'task quality'}" for row in rows if not row["task_pass"]]
    report="\n".join(lines)+"\n"
    (directory/"REPORT.txt").write_text(report,encoding="utf-8")
    (directory/"dashboard.html").write_text("<!doctype html><html lang='en'><meta charset='utf-8'><title>Phase 2 evaluations</title><style>body{max-width:1100px;margin:40px auto;font:16px/1.6 system-ui;color:#173f35}pre{white-space:pre-wrap}details{padding:12px;border:1px solid #ddd;margin:10px}</style><h1>Phase 2 agent evaluations</h1><pre>"+html.escape(report)+"</pre>"+"".join("<details><summary>"+html.escape(f"{r['case_id']} · {r['mode']} · repeat {r['repeat']} · {'PASS' if r['task_pass'] else 'FAIL'}")+"</summary><pre>"+html.escape(json.dumps(r,indent=2))+"</pre></details>" for r in rows)+"</html>",encoding="utf-8")
    return summaries


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live",action="store_true")
    parser.add_argument("--repeats",type=int,default=3)
    parser.add_argument("--max-cost",type=float,default=1)
    args=parser.parse_args()
    if not 1<=args.repeats<=10 or not 0<args.max_cost<=15:
        parser.error("Use 1-10 repeats and a positive cap up to $15")
    dataset=json.loads(DATASET.read_text(encoding="utf-8"))
    store=Store()
    provider=Fireworks(store) if args.live else None
    if provider and not provider.ready:
        parser.error("Live provider is not configured")
    before=store.spent()
    if provider:
        provider.cap=min(provider.cap,before+args.max_cost)
    stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    directory=ROOT/"docs"/"evals"/("phase2-"+stamp)
    directory.mkdir(parents=True,exist_ok=False)
    fingerprint=hashlib.sha256(DATASET.read_bytes()).hexdigest()
    source_fingerprint=hashlib.sha256("\n".join((ROOT/"equalstart"/name).read_text(encoding="utf-8") for name in ("agents.py","research.py","workflow.py","preparation.py")).encode()).hexdigest()
    metadata={"run_id":"phase2-"+stamp,"started_utc":datetime.now(timezone.utc).isoformat(),"prompt_version":PROMPT_VERSION,
              "dataset_version":dataset["version"],"dataset_fingerprint":fingerprint,"source_fingerprint":source_fingerprint,
              "annotation":dataset["annotation"],"model":provider.model if provider else "local baseline",
              "live":args.live,"initial_ledger_usd":before,"additional_eval_cap_usd":args.max_cost,"repeats":args.repeats,
              "cost_attribution":"Provider request IDs; settled usage or retained reservation",
              "model_config":{"temperature":0,"reasoning_effort":"low","max_output_tokens":4096},
              "gates":{"contract_rate":1.0,"task_pass_rate":.9}}
    (directory/"cases.json").write_text(json.dumps(dataset,indent=2),encoding="utf-8")
    rows=[]
    with (directory/"journal.jsonl").open("w",encoding="utf-8") as journal:
        for repeat in range(1,args.repeats+1):
            for case in dataset["cases"]:
                for mode, implementation in [("baseline",Phase2Baseline())]+([("live",provider)] if provider else []):
                    row=evaluate_case(case,implementation,mode,repeat,store if mode=="live" else None)
                    rows.append(row)
                    journal.write(json.dumps(row)+"\n")
                    journal.flush()
                    write_report(directory,metadata,rows)
            print(f"Phase 2 repeat {repeat}/{args.repeats} recorded",flush=True)
    metadata.update(finished_utc=datetime.now(timezone.utc).isoformat(),final_ledger_usd=store.spent(),estimated_eval_delta_usd=provider.cost() if provider else 0.0)
    (directory/"metadata.json").write_text(json.dumps(metadata,indent=2),encoding="utf-8")
    summaries=write_report(directory,metadata,rows)
    print(json.dumps({"directory":str(directory),"summaries":summaries,"estimated_eval_delta_usd":metadata["estimated_eval_delta_usd"]}))
    return int(any(not s["release_gate"] for s in summaries if s["mode"]=="live"))


if __name__=="__main__":
    raise SystemExit(main())
