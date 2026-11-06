"""Reproducible per-agent quality evaluations with recorded baselines and receipts."""
import argparse
import csv
import hashlib
import html
import json
import platform
import statistics
import sys
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
from time import perf_counter

from equalstart.agents import PROMPT_VERSION, SPECS, invoke_agent
from equalstart.catalog import ROOT
from equalstart.providers import Fireworks
from equalstart.storage import Store
from evals.dataset import CASES, DATASET_VERSION

FIELDS = {"Discovery": "opportunity_ids", "Evidence": "unconfirmed_claim_ids", "Fit": "opportunity_ids", "Planning": "material_indices"}
GRADER_VERSION = "2026-11-02-v2"


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class Baseline:
    """Production local behavior: no learned relevance, no flags, score/source order."""
    def generate(self, role, instruction, context, schema):
        if role == "Discovery":
            values = [c["id"] for c in context["candidates"]]
        elif role == "Evidence":
            values = []
        elif role == "Fit":
            values = [m["id"] for m in sorted(context["matches"], key=lambda m: m["score"], reverse=True)]
        else:
            values = list(range(len(context["materials"])))
        return schema.model_validate({FIELDS[role]: values})


class CountedProvider:
    def __init__(self, provider):
        self.provider, self.calls, self.raw_response = provider, 0, None

    def generate(self, *args):
        self.calls += 1
        response = self.provider.generate(*args)
        self.raw_response = response.model_dump()
        return response


def score(case, values):
    expected, role = case["expected"], case["agent"]
    metrics = {}
    if role in ("Discovery", "Evidence"):
        target = set(expected["relevant_ids" if role == "Discovery" else "flag_ids"])
        actual = set(values)
        tp, fp, fn = len(actual & target), len(actual - target), len(target - actual)
        precision = tp / len(actual) if actual else float(not target)
        recall = tp / len(target) if target else float(not actual)
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        metrics.update(precision=precision, recall=recall, f1=f1, true_positive=tp, false_positive=fp, false_negative=fn)
        if role == "Discovery":
            metrics["reciprocal_rank"] = next((1 / (n + 1) for n, value in enumerate(values) if value in target), float(not target and not values))
            passed = precision >= .8 and recall >= .8
        else:
            passed = f1 >= .8
    else:
        pairs = expected["before_pairs"]
        positions = {v: i for i, v in enumerate(values)}
        correct = sum(a in positions and b in positions and positions[a] < positions[b] for a, b in pairs)
        metrics["pairwise_order"] = correct / len(pairs) if pairs else 1.0
        metrics["labeled_pairs"] = len(pairs)
        passed = metrics["pairwise_order"] == 1.0
    return metrics, passed


def evaluate(case, provider, repeat, mode, store=None):
    started = perf_counter()
    counted = CountedProvider(provider)
    before = provider.cost() if store else 0
    row = {"case_id": case["id"], "agent": case["agent"], "slice": case["slice"], "repeat": repeat, "mode": mode,
           "contract_valid": False, "task_pass": False, "output": None, "error_type": None, "metrics": {}}
    try:
        output = invoke_agent(case["agent"], counted, case["context"])
        values = getattr(output, FIELDS[case["agent"]])
        row["output"] = values
        row["contract_valid"] = True
        row["metrics"], row["task_pass"] = score(case, values)
    except Exception as error:
        # Error types are sufficient for diagnosis without recording provider headers or keys.
        row["error_type"] = type(error).__name__
        if case["agent"] in ("Discovery", "Evidence"):
            row["metrics"] = {"precision": 0.0, "recall": 0.0, "f1": 0.0}
            if case["agent"] == "Discovery":
                row["metrics"]["reciprocal_rank"] = 0.0
        else:
            row["metrics"] = {"pairwise_order": 0.0, "labeled_pairs": len(case["expected"]["before_pairs"])}
        if counted.raw_response is not None:
            row["output"] = counted.raw_response.get(FIELDS[case["agent"]])
    row["model_calls"] = counted.calls if mode == "live" else 0
    row["latency_ms"] = round((perf_counter() - started) * 1000, 3)
    row["estimated_cost_delta_usd"] = round(provider.cost() - before, 9) if store else 0
    return row


def percentile(values, fraction):
    values = sorted(values)
    if not values:
        return None
    pos = (len(values) - 1) * fraction
    lo, hi = int(pos), min(int(pos) + 1, len(values) - 1)
    return values[lo] + (values[hi] - values[lo]) * (pos - lo)


def summarize(rows):
    summaries = []
    for agent in SPECS:
        for mode in sorted({r["mode"] for r in rows}):
            group = [r for r in rows if r["agent"] == agent and r["mode"] == mode]
            if not group:
                continue
            live_rows = [r for r in group if r["model_calls"]]
            latencies = [r["latency_ms"] for r in live_rows or group]
            metrics = {}
            for name in ("precision", "recall", "f1", "reciprocal_rank", "pairwise_order", "action_accuracy", "finding_accuracy"):
                values = [r["metrics"][name] for r in group if name in r["metrics"]]
                if values:
                    metrics[name] = statistics.mean(values)
            outputs = {}
            for row in group:
                outputs.setdefault(row["case_id"], []).append(json.dumps(row["output"]))
            repeated = [v for v in outputs.values() if len(v) > 1]
            stability = statistics.mean(len(set(v)) == 1 for v in repeated) if repeated else None
            slices = {s: {"passed": sum(r["task_pass"] for r in group if r["slice"] == s), "total": sum(r["slice"] == s for r in group)} for s in sorted({r["slice"] for r in group})}
            contract = sum(r["contract_valid"] for r in group) / len(group)
            quality = sum(r["task_pass"] for r in group) / len(group)
            summaries.append({"agent": agent, "mode": mode, "cases": len(outputs), "evaluations": len(group),
                              "model_calls": sum(r["model_calls"] for r in group), "contract_rate": contract,
                              "task_pass_rate": quality, "task_passes": sum(r["task_pass"] for r in group),
                              "metrics": metrics, "exact_output_stability": stability,
                              "latency_p50_ms": statistics.median(latencies), "latency_p95_ms": percentile(latencies, .95),
                              "estimated_cost_delta_usd": sum(r["estimated_cost_delta_usd"] for r in group),
                              "slices": slices, "release_gate": contract == 1 and quality >= .9})
    return summaries


def write_reports(directory, metadata, rows):
    summaries = summarize(rows)
    result = {"metadata": metadata, "summaries": summaries, "results": rows}
    (directory / "results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    with (directory / "results.csv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["agent", "mode", "case_id", "slice", "repeat", "contract_valid", "task_pass", "model_calls", "latency_ms", "estimated_cost_delta_usd", "error_type", "output", "metrics"])
        writer.writeheader()
        writer.writerows({**r, "output": json.dumps(r["output"]), "metrics": json.dumps(r["metrics"])} for r in rows)
    lines = ["# Equal Start agent evaluation report", "", f"Run: {metadata['run_id']}. Model: {metadata['model']}. Prompt: {metadata['prompt_version']}. Dataset: {metadata['dataset_version']}.", "",
             "Fixed synthetic development cases, repeated per run configuration. Per-agent counts are recorded below. Expected labels are excluded from model requests. This is not independently held-out data or a student usability study.", "",
             "| Agent | Mode | Passed / evaluated | Contract | Task pass | Model calls | p50 / p95 ms | Gate |",
             "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for s in summaries:
        lines.append(f"| {s['agent']} | {s['mode']} | {s['task_passes']} / {s['evaluations']} | {s['contract_rate']:.1%} | {s['task_pass_rate']:.1%} | {s['model_calls']} | {s['latency_p50_ms']:.0f} / {s['latency_p95_ms']:.0f} | {'PASS' if s['release_gate'] else 'FAIL'} |")
    lines += ["", "## Diagnostic metrics", "", "Macro means across cases; task pass and contract rates above are the primary gates.", "",
              "| Agent | Mode | Precision | Recall | F1 | Reciprocal rank | Pair ordering | Exact repeat stability | Estimated cost delta |",
              "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for s in summaries:
        cells = [f"{s['metrics'][key]:.3f}" if key in s["metrics"] else "n/a" for key in ("precision", "recall", "f1", "reciprocal_rank", "pairwise_order")]
        stable = f"{s['exact_output_stability']:.1%}" if s["exact_output_stability"] is not None else "n/a"
        lines.append(f"| {s['agent']} | {s['mode']} | " + " | ".join(cells) + f" | {stable} | ${s['estimated_cost_delta_usd']:.6f} |")
    lines += ["", "## Scoring and gates", "",
              "Discovery: set precision and recall against relevant candidate IDs must each reach 0.80 per case; reciprocal rank is also recorded. Evidence: flag precision, recall and F1 against explicitly ambiguous/unsupported summaries, with F1 at least 0.80. Fit: every labeled preference pair must be ordered correctly. Planning: every labeled prerequisite pair must be ordered correctly. All agents must return valid schemas, grounded references and no duplicates; Fit and Planning must preserve complete input sets.", "",
              "Each agent's live release gate requires 100% contract validity and at least 90% task-case passes. Cases without preference pairs still check contracts but supply no preference-quality evidence. Empty cases test the deterministic no-call guard and are reported separately by slice. Exact-output stability is descriptive: tied or flexible orders can differ without failing task quality.", "",
              "## Failures", ""]
    failed = [r for r in rows if not r["task_pass"]]
    if not failed:
        lines.append("No failed cases in this run.")
    for row in failed:
        case = next(c for c in CASES if c["id"] == row["case_id"])
        lines += [f"- {row['agent']} {row['case_id']} · {row['mode']} · repeat {row['repeat']}: output `{json.dumps(row['output'])}`, expected `{json.dumps(case['expected'])}`, error `{row['error_type']}`."]
    lines += ["", "## Interpretation and limits", "",
              "The baseline is the app's simple local behavior on already-screened inputs: keep all discovery candidates, flag no claims, rank by supplied heuristic score, and preserve source material order. It is not a competing frontier model. Models and baselines use identical labeled contexts; labels are never sent to the model. No LLM judges its own answer.", "",
              "Evidence evaluates ambiguity in stored summaries, not external factual truth or citation entailment against full source text. Fit does not decide eligibility, and Planning only sequences supplied materials. Separate unit tests cover deterministic eligibility and guard rejection. Three repeats of one case are correlated, so percentages are descriptive and no significance or population-accuracy claim is made.", "",
              "API errors and malformed output remain failed evaluations; production fallbacks do not turn failures into passes. Grader v2 assigns zero diagnostic quality to contract failures so averages cannot exclude those failures. Latency measures wrapper wall time, with deterministic empty guards excluded from live-call latency summaries. Cost is the shared ledger delta including retained reservations, not independently audited provider billing. The persistent $15 authorization remains in force.", "",
              f"Source fingerprint: `{metadata['source_fingerprint']}`. Dataset fingerprint: `{metadata['dataset_fingerprint']}`. Full contexts, labels and reasons are in cases.json; individual repeats, slices, metrics and errors are in results.json/CSV."]
    (directory / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    cards = []
    for s in summaries:
        cards.append(f"<article><h2>{s['agent']} <small>{s['mode']}</small></h2><strong>{s['task_pass_rate']:.1%}</strong><p>{s['task_passes']}/{s['evaluations']} task cases passed · {s['contract_rate']:.0%} contract validity</p><progress max='1' value='{s['task_pass_rate']}'></progress><p>{s['model_calls']} model calls · p50 {s['latency_p50_ms']:.0f} ms · gate {'PASS' if s['release_gate'] else 'FAIL'}</p></article>")
    details = "".join(f"<details><summary>{r['agent']} {r['case_id']} · {r['mode']} · repeat {r['repeat']} · {'PASS' if r['task_pass'] else 'FAIL'}</summary><pre>{html.escape(json.dumps(r,indent=2))}</pre></details>" for r in rows)
    (directory / "dashboard.html").write_text("<!doctype html><html lang='en'><meta charset='utf-8'><meta name='viewport' content='width=device-width'><title>Equal Start agent evaluations</title><style>body{font:16px system-ui;background:#faf9f5;color:#173632;max-width:1200px;margin:40px auto;padding:20px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:16px}article,details{background:white;padding:20px;border:1px solid #dce5dc;border-radius:14px;margin:10px 0}strong{font-size:36px}small{font-size:14px;color:#61756c}progress{width:100%;accent-color:#087f72}pre{white-space:pre-wrap;overflow-wrap:anywhere}summary{cursor:pointer}</style><h1>Equal Start agent evaluations</h1><p>Fixed synthetic cases, deterministic scoring, recorded failures. See REPORT.md for definitions and limitations.</p><div class='grid'>" + "".join(cards) + "</div><h2>Individual evaluations</h2>" + details + "</html>", encoding="utf-8")
    return summaries


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--max-cost", type=float, default=1.0, help="Additional eval-only cap, within existing $15 total")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not 1 <= args.repeats <= 10 or not 0 < args.max_cost <= 15:
        parser.error("Use 1–10 repeats and a positive additional cap no greater than $15")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    directory = args.output or ROOT / "docs" / "evals" / stamp
    directory.mkdir(parents=True, exist_ok=False)
    store = Store()
    provider = Fireworks(store) if args.live else None
    if args.live and not provider.ready:
        parser.error("Live Fireworks credentials and model prices must be configured")
    before = store.spent()
    if provider:
        provider.cap = min(provider.cap, before + args.max_cost)
    metadata = {"run_id": stamp, "started_utc": datetime.now(timezone.utc).isoformat(), "model": provider.model if provider else "local baseline only",
                "prompt_version": PROMPT_VERSION, "grader_version": GRADER_VERSION, "dataset_version": DATASET_VERSION, "dataset_fingerprint": digest(CASES),
                "source_fingerprint": digest({"specs": {role: (schema.model_json_schema(), instruction) for role, (schema, instruction) in SPECS.items()},
                                              "agents_source": (ROOT / "equalstart" / "agents.py").read_text(encoding="utf-8"),
                                              "provider_source": (ROOT / "equalstart" / "providers.py").read_text(encoding="utf-8")}),
                "repeats": args.repeats, "case_counts": {role:sum(case['agent']==role for case in CASES) for role in SPECS},
                "provider": getattr(provider,"provider","local"),
                "python": platform.python_version(), "pydantic": version("pydantic"), "langgraph": version("langgraph"),
                "model_config": {"temperature": 0, "reasoning_effort": "low", "max_output_tokens": 4096,
                                 "input_per_million_usd": provider.input_rate if provider else None,
                                 "output_per_million_usd": provider.output_rate if provider else None},
                "initial_ledger_usd": before, "additional_eval_cap_usd": args.max_cost, "live": args.live,
                "cost_attribution": "Provider request IDs; settled usage or retained reservation, independent of concurrent runs",
                "gates": {"contract_rate": 1.0, "task_pass_rate": .9}}
    (directory / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    (directory / "cases.json").write_text(json.dumps(CASES, indent=2), encoding="utf-8")
    rows = []
    with (directory / "journal.jsonl").open("w", encoding="utf-8") as journal:
        for agent in SPECS:
            for repeat in range(1, args.repeats + 1):
                for case in [c for c in CASES if c["agent"] == agent]:
                    for mode, implementation in [("baseline", Baseline())] + ([("live", provider)] if provider else []):
                        row = evaluate(case, implementation, repeat, mode, store if mode == "live" else None)
                        rows.append(row)
                        journal.write(json.dumps(row) + "\n")
                        journal.flush()
                print(f"{agent}: repeat {repeat}/{args.repeats} recorded", flush=True)
                write_reports(directory, metadata, rows)
    metadata["finished_utc"] = datetime.now(timezone.utc).isoformat()
    metadata["final_ledger_usd"] = store.spent()
    metadata["estimated_eval_delta_usd"] = provider.cost() if provider else 0.0
    (directory / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    summaries = write_reports(directory, metadata, rows)
    print(json.dumps({"report": str(directory), "summaries": summaries, "estimated_eval_delta_usd": metadata["estimated_eval_delta_usd"]}), flush=True)
    return int(any(not s["release_gate"] for s in summaries if s["mode"] == "live"))


if __name__ == "__main__":
    sys.exit(main())
