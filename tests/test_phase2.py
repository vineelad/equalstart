from datetime import datetime, timezone, timedelta, date
from types import SimpleNamespace

import pytest

from equalstart.agents import invoke_agent
from equalstart.catalog import load_catalog
from equalstart.preparation import validate_dependencies, outreach_drafts
from equalstart.readiness import readiness
from equalstart.research import research_sources, retrieve_source, snapshot_from
from equalstart.schema import GroundedEvidenceOutput, GroundedFinding, Profile, ResearchAction, Task
from equalstart.storage import Store
from equalstart.workflow import application_tasks, run_matching

NOW = datetime(2026, 11, 3, 3, tzinfo=timezone.utc)


def record():
    return load_catalog()[0]


class Result:
    ready = True
    def __init__(self, output):
        self.output = output
    def generate(self, *args):
        return self.output


def grounded_context():
    return {"claims": [{"id": "c", "opportunity_id": "r", "text": "Up to $100"}],
            "sources": [{"id": "s", "opportunity_id": "r", "content": "Selected students receive up to $100."}]}


@pytest.mark.parametrize("status,quote,source,claim", [
    ("Supported", "Invented quote", "s", "c"),
    ("Supported", "", "s", "c"),
    ("Supported", "up to $100", "other", "c"),
    ("Not found", "up to $100", "s", "c"),
    ("Supported", "up to $100", "s", "invented"),
])
def test_evidence_rejects_ungrounded_findings(status, quote, source, claim):
    output = GroundedEvidenceOutput(findings=[GroundedFinding(claim_id=claim, snapshot_id=source, status=status, quote=quote)])
    with pytest.raises(ValueError):
        invoke_agent("Evidence", Result(output), grounded_context())


def test_evidence_cannot_borrow_another_opportunitys_source():
    context = grounded_context()
    context["sources"][0]["opportunity_id"] = "someone-else"
    output = GroundedEvidenceOutput(findings=[GroundedFinding(claim_id="c", snapshot_id="s", status="Supported", quote="up to $100")])
    with pytest.raises(ValueError):
        invoke_agent("Evidence", Result(output), context)


def test_exact_supported_quote_is_valid_but_does_not_verify_eligibility():
    output = GroundedEvidenceOutput(findings=[GroundedFinding(claim_id="c", snapshot_id="s", status="Supported", quote="up to $100")])
    assert invoke_agent("Evidence", Result(output), grounded_context()).findings[0].status == "Supported"


def test_passage_selection_copies_exact_source_text_without_model_transcription():
    output=GroundedEvidenceOutput(findings=[GroundedFinding(claim_id="c",snapshot_id="s",status="Supported",passage_index=0)])
    finding=invoke_agent("Evidence",Result(output),grounded_context()).findings[0]
    assert finding.quote==grounded_context()["sources"][0]["content"]
    bad=GroundedEvidenceOutput(findings=[GroundedFinding(claim_id="c",snapshot_id="s",status="Supported",passage_index=100)])
    with pytest.raises(ValueError):
        invoke_agent("Evidence",Result(bad),grounded_context())


@pytest.mark.parametrize("action,rid", [("search", ""), ("fetch", "evil"), ("finish", "r")])
def test_tool_action_is_limited_to_available_actions_and_ids(action, rid):
    context = {"research_state": {"available_actions": ["fetch", "finish"], "fetchable_ids": ["r"]}}
    with pytest.raises(ValueError):
        invoke_agent("Discovery", Result(ResearchAction(action=action, opportunity_id=rid)), context)


def test_fresh_source_is_reused_and_stale_source_refetched(tmp_path):
    item = record()
    store = Store(tmp_path / "db.sqlite")
    class Client:
        calls = 0
        def fetch(self, url, hosts):
            self.calls += 1
            return {"content": "Current provider page text."}
    client = Client()
    first, _ = retrieve_source(item, client, store, NOW)
    second, status = retrieve_source(item, client, store, NOW+timedelta(minutes=30))
    assert first.id == second.id and client.calls == 1 and status == "Cached source"
    retrieve_source(item, client, store, NOW+timedelta(hours=7))
    assert client.calls == 2


def test_source_cannot_be_created_for_a_model_proposed_host():
    with pytest.raises(ValueError):
        snapshot_from(record(), "https://evil.example/award", "text", NOW)


def test_bounded_research_terminates_on_repeated_search():
    class Client:
        calls = 0
        def search(self, query):
            self.calls += 1
            return []
    client = Client()
    result = research_sources(Profile(goal="Find funding", citizenship="US citizen"), [record()],
                              Result(ResearchAction(action="search")), client, allow_clarification=False)
    assert client.calls <= 2
    assert result["rounds"] <= 6
    assert result["stop_reason"]


def test_missing_optional_answer_stays_unknown_and_is_only_asked_once():
    profile = Profile(goal="Find research", citizenship=None)
    result = research_sources(profile, [record()], allow_clarification=True)
    assert result["clarification"]["field"] == "citizenship"
    skipped = research_sources(profile, [record()], allow_clarification=False)
    assert skipped["clarification"] is None and profile.citizenship is None


def test_unavailable_source_does_not_become_a_verified_finding():
    class Offline:
        def fetch(self, *args):
            raise TimeoutError()
        def search(self, *args):
            return []
    profile = Profile(goal="Environmental research", citizenship="US citizen")
    result = research_sources(profile, [record()], client=Offline(), allow_clarification=False)
    assert result["snapshots"] == []
    assert any(step["status"] == "Unavailable" for step in result["trace"])


def test_evidence_handoff_reaches_fit_and_does_not_override_rules():
    from equalstart.schema import DiscoveryOutput, EvidenceOutput, FitOutput
    contexts = []
    class Provider:
        ready = True
        def generate(self, role, instruction, context, schema):
            if role == "Discovery":
                if "research_state" in context:
                    return ResearchAction(action="fetch", opportunity_id=context["research_state"]["fetchable_ids"][0])
                return DiscoveryOutput(opportunity_ids=[c["id"] for c in context["candidates"]])
            if role == "Evidence":
                return GroundedEvidenceOutput(findings=[GroundedFinding(claim_id=c["id"], snapshot_id=context["sources"][0]["id"], status="Not found", quote="") for c in context["claims"]])
            contexts.append(context)
            return FitOutput(opportunity_ids=[m["id"] for m in context["matches"]])
    class Client:
        def search(self, *args): return []
        def fetch(self, *args): return {"content": "Provider information without the relevant funding terms."}
    result = run_matching(Profile(goal="Environmental research", citizenship="US citizen"), [record()], Provider(), NOW,
                          Client(), allow_clarification=False)
    assert contexts[0]["matches"][0]["evidence_needs_confirmation"]
    assert result["findings"] and result["flagged_claims"]


def test_research_trace_does_not_persist_profile_or_arbitrary_payload(tmp_path):
    store = Store(tmp_path / "test.sqlite")
    store.log_research("run", [{"action": "fetch", "status": "Complete", "profile": "private", "goal": "private"}])
    with store.connect() as con:
        trace = con.execute("SELECT trace FROM research").fetchone()[0]
    assert "private" not in trace and "fetch" in trace


def test_eval_cost_attribution_ignores_another_runs_reservation_settlement(tmp_path):
    store=Store(tmp_path/"cost.sqlite")
    mine=store.reserve(1)
    other=store.reserve(2)
    assert store.cost_for_calls([mine])==1
    store.settle(other,.01)
    assert store.cost_for_calls([mine])==1
    store.settle(mine,.2)
    assert store.cost_for_calls([mine])==pytest.approx(.2)
    assert store.cost_for_calls([])==0


def test_suggested_dates_missing_deadlines_and_dependency_cycles():
    item = record().model_copy(update={"deadline": None, "deadline_date": None})
    tasks, _ = application_tasks(item, today=date(2026, 11, 2))
    assert all(task.suggested_date is None for task in tasks)
    assert tasks[1].id == "costs"
    validate_dependencies(tasks)
    with pytest.raises(ValueError):
        validate_dependencies([Task(id="a", text="A", kind="suggestion", depends_on=["b"]), Task(id="b", text="B", kind="suggestion", depends_on=["a"])])


def test_drafts_are_editable_templates_without_invented_contacts():
    drafts = outreach_drafts(record())
    assert len(drafts) == 3
    assert all(str(record().official_url) in draft for draft in drafts.values())
    assert all("@" not in draft for draft in drafts.values())


def test_no_fresh_evidence_is_not_represented_as_verified():
    from equalstart.eligibility import assess
    item = record()
    result = readiness(item, assess(Profile(goal="Find funding"), item), [])
    assert result["supported"] == 0 and "not assessed" in result["evidence"]


@pytest.mark.parametrize("details", [
    {"goal":"Community college transfer tuition support", "institution_type":"Community college", "transfer_plans":True},
    {"goal":"Funded environmental research", "no_upfront":True, "needs_housing":True},
    {"goal":"Undergraduate tuition support", "citizenship":None},
    {"goal":"Find undergraduate scholarships", "citizenship":"International student"},
    {"goal":"Find funding with unresolved requirements", "gpa":None},
    {"goal":"Undergraduate opportunities in an unavailable subject", "discipline":"Arts and humanities"},
])
def test_six_student_journeys_preserve_rules_and_honest_uncertainty(details):
    profile = Profile(**details)
    result = run_matching(profile, load_catalog(), now=NOW)
    matches = {match.opportunity_id:match for match in result["matches"]}
    assert all(matches[rid].status != "Not eligible" and matches[rid].cycle_status != "Closed" for rid in result["selected_ids"])
    assert all(event.mode == "Local baseline" for event in result["events"])
    assert all(finding["status"] != "Supported" for finding in result.get("findings", []))


def test_phase2_dataset_and_graders_cover_each_role_without_label_leakage():
    import json
    from collections import Counter
    from evals.phase2 import DATASET, Phase2Baseline, evaluate_case
    dataset=json.loads(DATASET.read_text(encoding="utf-8"))
    assert Counter(case["agent"] for case in dataset["cases"]) == {"Discovery":5,"Evidence":5,"Fit":5,"Planning":5}
    for case in dataset["cases"]:
        assert "expected" not in case["context"]
        assert evaluate_case(case,Phase2Baseline(),"baseline",1)["contract_valid"]


def test_student_can_compare_two_options_and_browse_the_catalog(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest
    from equalstart.catalog import ROOT
    monkeypatch.setenv("FIREWORKS_API_KEY", "")
    monkeypatch.setenv("EQUALSTART_DB_PATH", str(tmp_path/"comparison.sqlite"))
    app=AppTest.from_file(ROOT/"app.py",default_timeout=30).run()
    next(button for button in app.button if button.key=="sample-profile").click().run()
    assert sum(button.label.startswith("View opportunity") for button in app.button)==3
    app.multiselect[0].set_value(["noaa-hollings","doe-suli"]).run()
    assert app.multiselect[0].value == ["noaa-hollings","doe-suli"]
    assert not app.exception
    app.radio[0].set_value("Browse reviewed catalog").run()
    assert sum(button.label.startswith("View opportunity") for button in app.button)>3


def test_evidence_gap_can_trigger_only_one_additional_reviewed_fetch():
    item=record()
    alt="https://www.noaa.gov/synthetic-reviewed-funding"
    from pydantic import HttpUrl
    claims=[claim.model_copy(update={"url":HttpUrl(alt)}) if claim.topic=="funding" else claim for claim in item.claims]
    item=item.model_copy(update={"claims":claims})
    from equalstart.schema import DiscoveryOutput, FitOutput
    class Provider:
        ready=True
        def generate(self,role,instruction,context,schema):
            if role=="Discovery":
                if "research_state" in context:
                    return ResearchAction(action="fetch",opportunity_id=context["research_state"]["fetchable_ids"][0])
                return DiscoveryOutput(opportunity_ids=[item.id])
            if role=="Evidence":
                return GroundedEvidenceOutput(findings=[GroundedFinding(claim_id=c["id"],snapshot_id=context["sources"][0]["id"],status="Not found",quote="") for c in context["claims"]])
            return FitOutput(opportunity_ids=[item.id])
    class Client:
        calls=[]
        def search(self,*args): return []
        def fetch(self,url,*args):
            self.calls.append(url)
            return {"content":"No complete funding terms were found."}
    client=Client()
    result=run_matching(Profile(goal="Environmental research",citizenship="US citizen"),[item],Provider(),NOW,client,allow_clarification=False)
    assert client.calls==[str(item.official_url),alt]
    assert result["evidence_retry_done"] and result["research_fetches"]==2
    assert sum(step["action"]=="evidence-followup" for step in result["research_trace"])==1
