from datetime import datetime

import pytest
from pydantic import ValidationError

from equalstart.catalog import load_catalog
from equalstart.eligibility import assess, cycle_status
from equalstart.schema import Profile
from equalstart.storage import Store
from equalstart.workflow import application_tasks, run_matching

NOW = datetime.fromisoformat("2026-11-02T10:00:00-06:00")


@pytest.fixture
def records():
    return {r.id: r for r in load_catalog()}


def profile(**overrides):
    return Profile(**({"goal": "I want environmental research and financial support", "citizenship": "US citizen", "gpa": 3.5, "full_time": True, "research_career": True} | overrides))


def test_catalog_evidence_and_unique_ids(records):
    assert len(records) >= 20
    for r in records.values():
        assert str(r.official_url).startswith("https://")
        assert r.country == "US"
        assert all(rule.claim_id in {c.id for c in r.claims} for rule in r.rules)


def test_citizenship_is_not_inferred(records):
    item = records["noaa-hollings"]
    assert assess(profile(citizenship="International student"), item, NOW).status == "Not eligible"
    missing = assess(profile(citizenship=None), item, NOW)
    assert missing.status == "Needs confirmation"
    assert next(c for c in missing.criteria if c.label == "U.S. citizenship").state == "Unknown"


def test_permanent_resident_does_not_meet_citizen_only_award(records):
    assert assess(profile(citizenship="Permanent resident"), records["noaa-hollings"], NOW).status == "Not eligible"


def test_cci_and_suli_have_distinct_requirements(records):
    student = profile(institution_type="Community college", gpa=2.8)
    assert assess(student, records["doe-cci"], NOW).status == "Needs confirmation"
    assert assess(student, records["doe-suli"], NOW).status == "Not eligible"
    assert assess(profile(institution_type="Four-year"), records["doe-cci"], NOW).status == "Not eligible"


def test_or_gpa_requirement_is_not_simplified_to_false_failure(records):
    assert assess(profile(gpa=3.1), records["nih-ugsp"], NOW).status != "Not eligible"
    assert any("top-five" in c.label for c in assess(profile(gpa=3.1), records["nih-ugsp"], NOW).criteria)


def test_reimbursement_never_becomes_upfront_support(records):
    result = assess(profile(no_upfront=True), records["doe-suli"], NOW)
    assert any("reimbursed" in b for b in result.barriers)
    assert any("Housing is not provided" in b for b in assess(profile(), records["nih-sip"], NOW).barriers)


def test_deadline_timezones_and_date_only_uncertainty(records):
    assert cycle_status(records["cmu-reuse"], NOW) == "Closed"
    assert cycle_status(records["ncsa-reu"], NOW) == "Upcoming"
    assert cycle_status(records["ncsa-reu"], datetime.fromisoformat("2026-11-16T10:00:00-06:00")) == "Open"
    assert cycle_status(records["ud-first-generation"], datetime.fromisoformat("2026-11-04T10:00:00-06:00")) == "Confirm closing time"
    assert cycle_status(records["noaa-hollings"], datetime.fromisoformat("2027-01-31T23:00:00-06:00")) == "Closed"


def test_local_graph_never_claims_live_execution(records):
    result = run_matching(profile(), list(records.values()), now=NOW)
    assert [e.stage for e in result["events"]] == ["Discovery", "Evidence", "Fit"]
    assert all(e.mode == "Local baseline" for e in result["events"])
    assert "cmu-reuse" not in result["selected_ids"]


def test_live_invalid_ids_fall_back_without_overriding_rules(records):
    from equalstart.schema import DiscoveryOutput

    class BadProvider:
        ready = True

        def generate(self, *args):
            return DiscoveryOutput(opportunity_ids=["fabricated-award"])

    result = run_matching(profile(citizenship="International student"), list(records.values()), BadProvider(), NOW)
    assert any(e.status == "Fallback" for e in result["events"])
    assert "fabricated-award" not in result["selected_ids"]
    assert "noaa-hollings" not in result["selected_ids"]


def test_goal_changes_relevance(records):
    computing = assess(profile(goal="Python computing machine learning open source tools", discipline="STEM"), records["ncsa-reu"], NOW)
    arts = assess(profile(goal="Humanities tuition support literary arts", discipline="Arts and humanities"), records["ncsa-reu"], NOW)
    assert computing.score > arts.score


def test_local_saves_and_cost_ledger_are_independent(tmp_path):
    db = Store(tmp_path / "test.sqlite")
    db.save("noaa-hollings")
    db.tasks("noaa-hollings", ["verify"])
    db.save_plan("noaa-hollings", [{"id": "verify", "text": "Check source"}])
    assert Store(tmp_path / "test.sqlite").saved()["noaa-hollings"] == ["verify"]
    assert Store(tmp_path / "test.sqlite").plan("noaa-hollings")[0]["id"] == "verify"
    call = db.reserve(1, 15)
    db.settle(call, 0.3)
    pending = db.reserve(0.5)
    db.settle(pending, None)
    assert db.spent() == pytest.approx(0.8)
    with pytest.raises(RuntimeError):
        db.reserve(14.3)
    db.clear_saved()
    assert db.saved() == {}
    assert db.spent() == pytest.approx(0.8)
    with pytest.raises(ValueError):
        db.reserve(1, 16)


def test_planner_separates_official_and_suggested_tasks(records):
    tasks, event = application_tasks(records["nih-sip"])
    assert event.mode == "Local baseline"
    assert all(t.source_url for t in tasks)
    assert {t.kind for t in tasks} == {"Published material or process", "Suggested preparation"}


def test_naive_precise_deadlines_are_rejected(records):
    item = records["noaa-hollings"].model_dump()
    item["deadline"] = datetime(2027, 1, 31)
    with pytest.raises(ValidationError):
        type(records["noaa-hollings"]).model_validate(item)


def test_institution_names_ignore_case_and_extra_spaces(records):
    match = assess(profile(institution=" university  of DALLAS "), records["ud-first-generation"], NOW)
    assert match.criteria[0].state == "Met"


def test_dreamer_award_excludes_known_ineligible_statuses(records):
    for status in ("US citizen", "Permanent resident", "International student"):
        assert assess(profile(citizenship=status), records["dream-national"], NOW).status == "Not eligible"
    assert assess(profile(citizenship="DACA"), records["dream-national"], NOW).status == "Needs confirmation"


def test_conflicting_source_rules_are_not_silently_resolved(records):
    match = assess(profile(), records["cobell-undergrad"], NOW)
    assert any("conflicts" in c.label and c.state == "Unknown" for c in match.criteria)
