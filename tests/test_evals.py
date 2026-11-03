from collections import Counter
from types import SimpleNamespace

import pytest

from equalstart.agents import invoke_agent
from evals.dataset import CASES
from evals.runner import Baseline, FIELDS, evaluate, score, summarize


def test_fixed_dataset_has_eight_distinct_cases_per_agent():
    assert Counter(c["agent"] for c in CASES) == {"Discovery": 8, "Evidence": 8, "Fit": 8, "Planning": 8}
    assert len({c["id"] for c in CASES}) == 32
    for case in CASES:
        assert case["label_reason"]
        assert "expected" not in case["context"]


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_baseline_contracts_and_perfect_reference_scoring(case):
    row = evaluate(case, Baseline(), 1, "baseline")
    assert row["contract_valid"]
    if case["agent"] == "Discovery":
        answer = case["expected"]["relevant_ids"]
    elif case["agent"] == "Evidence":
        answer = case["expected"]["flag_ids"]
    else:
        count = len(case["context"]["matches"] if case["agent"] == "Fit" else case["context"]["materials"])
        # Validate label references; ordering quality is evaluated separately.
        valid = {x["id"] for x in case["context"]["matches"]} if case["agent"] == "Fit" else set(range(count))
        assert all(a in valid and b in valid and a != b for a, b in case["expected"]["before_pairs"])
        return
    assert score(case, answer)[1]


class Fake:
    def __init__(self, data):
        self.data = data

    def generate(self, *args):
        return SimpleNamespace(model_dump=lambda: self.data)


@pytest.mark.parametrize("role,case_id,bad", [
    ("Discovery", "D01", ["outside-candidate-set"]),
    ("Discovery", "D01", ["climate", "climate"]),
    ("Evidence", "E01", ["invented-claim"]),
    ("Evidence", "E01", ["gpa", "gpa"]),
    ("Fit", "F01", ["advance"]),
    ("Fit", "F01", ["advance", "advance"]),
    ("Planning", "P01", [0, 1, 99]),
    ("Planning", "P01", [0, 1]),
])
def test_agent_guard_rejects_ungrounded_or_incomplete_outputs(role, case_id, bad):
    case = next(c for c in CASES if c["id"] == case_id)
    with pytest.raises(ValueError):
        invoke_agent(role, Fake({FIELDS[role]: bad}), case["context"])
    row = evaluate(case, Fake({FIELDS[role]: bad}), 1, "live")
    assert not row["contract_valid"] and not row["task_pass"]


@pytest.mark.parametrize("case_id", ["D06", "E08", "F08", "P07"])
def test_empty_inputs_do_not_spend_inference(case_id):
    class MustNotCall:
        def generate(self, *args):
            raise AssertionError("Empty input must not call a provider")
    case = next(c for c in CASES if c["id"] == case_id)
    row = evaluate(case, MustNotCall(), 1, "live")
    assert row["task_pass"] and row["model_calls"] == 0


def test_scorers_detect_semantic_errors_despite_valid_contracts():
    for case_id, output in [("D01", ["dance"]), ("E02", []), ("F01", ["reimburse", "advance"]), ("P01", [0, 1, 2])]:
        case = next(c for c in CASES if c["id"] == case_id)
        assert not score(case, output)[1]


def test_failure_accounting_never_hides_cases():
    cases = [c for c in CASES if c["agent"] == "Discovery"]
    rows = [evaluate(c, Baseline(), 1, "baseline") for c in cases]
    result = summarize(rows)[0]
    assert result["evaluations"] == 8
    assert result["task_passes"] < 8
    assert result["contract_rate"] == 1


def test_planner_receives_explicit_zero_based_indices():
    class Capture:
        def generate(self, role, instruction, context, schema):
            assert context["indexed_materials"] == [{"index": 0, "text": "Submit form"}, {"index": 1, "text": "Obtain form"}]
            return schema(material_indices=[1, 0])
    assert invoke_agent("Planning", Capture(), {"materials": ["Submit form", "Obtain form"]}).material_indices == [1, 0]


def test_invalid_contracts_receive_zero_diagnostic_quality():
    case = next(c for c in CASES if c["id"] == "P01")
    row = evaluate(case, Fake({"material_indices": [99]}), 1, "live")
    assert row["metrics"]["pairwise_order"] == 0
    assert row["output"] == [99]


def test_empty_discovery_is_preserved_and_later_stages_do_not_claim_model_calls():
    from equalstart.catalog import load_catalog
    from equalstart.schema import DiscoveryOutput, Profile
    from equalstart.workflow import application_tasks, run_matching

    class NoMatches:
        ready = True
        def generate(self, *args):
            return DiscoveryOutput(opportunity_ids=[])
    result = run_matching(Profile(goal="Find some undergraduate opportunities"), load_catalog(), NoMatches())
    assert result["selected_ids"] == []
    assert [e.mode for e in result["events"]] == ["Fireworks", "Local baseline", "Local baseline"]
    no_materials = next(r for r in load_catalog() if not r.materials)
    assert application_tasks(no_materials, NoMatches())[1].mode == "Local baseline"
