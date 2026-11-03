from datetime import datetime
from time import perf_counter
from typing import TypedDict
from uuid import uuid4

from langgraph.graph import END, START, StateGraph

from equalstart.eligibility import rank
from equalstart.agents import invoke_agent
from equalstart.providers import Fireworks, Keenable
from equalstart.schema import AgentEvent, Match, Opportunity, Profile, Task


class RunState(TypedDict, total=False):
    profile: Profile
    records: list[Opportunity]
    matches: list[Match]
    selected_ids: list[str]
    events: list[AgentEvent]
    flagged_claims: list[str]
    leads: list[dict]


def run_matching(profile: Profile, catalog: list[Opportunity], provider: Fireworks | None = None, now: datetime | None = None, search: Keenable | None = None) -> RunState:
    baseline = rank(profile, catalog, now)
    live = provider is not None and provider.ready

    def stage(name, function, fallback, state):
        started = perf_counter()
        requested_model = live and bool(initial if name == "Discovery" else state.get("selected_ids", []))
        actual_mode = "Fireworks" if requested_model else "Local baseline"
        try:
            updates, summary = function()
            event = AgentEvent(stage=name, mode=actual_mode, status="Complete", summary=summary, elapsed_ms=round((perf_counter()-started)*1000))
        except Exception as error:
            updates = fallback
            event = AgentEvent(stage=name, mode=actual_mode, status="Fallback", summary=f"{type(error).__name__}: retained validated local results. Check connection, budget, or model settings.", elapsed_ms=round((perf_counter()-started)*1000))
        updates["events"] = state.get("events", []) + [event]
        return updates

    allowed = {m.opportunity_id for m in baseline if m.status != "Not eligible" and m.cycle_status != "Closed"}
    initial = [m.opportunity_id for m in baseline if m.opportunity_id in allowed][:12]
    lookup = {r.id: r for r in catalog}

    def discovery(state):
        def work():
            ids = initial
            leads = []
            if search:
                try:
                    leads = search.search(f"undergraduate {profile.discipline} scholarships funded research USA")
                except Exception:
                    pass  # Reviewed retrieval works even when live discovery is unavailable.
            if live and ids:
                context = {"goal": profile.goal, "discipline": profile.discipline,
                           "candidates": [{"id": i, "title": lookup[i].title, "summary": lookup[i].summary, "tags": lookup[i].tags} for i in ids],
                           "web_leads_unverified": [{"title": str(x.get("title", ""))[:200], "url": x["url"]} for x in leads]}
                output = invoke_agent("Discovery", provider, context)
                if len(output.opportunity_ids) != len(set(output.opportunity_ids)) or not set(output.opportunity_ids).issubset(allowed):
                    raise ValueError("Unrecognized or duplicate discovery IDs")
                ids = output.opportunity_ids
            return {"selected_ids": ids, "leads": leads}, f"Catalog search returned {len(ids)} candidates after hard-rule and cycle screening. Keenable returned {len(leads)} separate, unverified discovery leads."
        return stage("Discovery", work, {"selected_ids": initial}, state)

    def evidence(state):
        def work():
            claims = [c.model_dump(mode="json") for i in state["selected_ids"] for c in lookup[i].claims]
            flagged = []
            if live and claims:
                output = invoke_agent("Evidence", provider, {"claims": claims})
                if not set(output.unconfirmed_claim_ids).issubset({c["id"] for c in claims}):
                    raise ValueError("Unknown evidence reference")
                flagged = output.unconfirmed_claim_ids
            return {"flagged_claims": flagged}, f"Inspected {len(claims)} stored evidence references; {len(flagged)} flagged for review. No live re-verification implied."
        return stage("Evidence", work, {"flagged_claims": []}, state)

    def fit(state):
        def work():
            selected = state["selected_ids"]
            if live and selected:
                context = {"goal": profile.goal, "no_upfront": profile.no_upfront, "needs_housing": profile.needs_housing,
                           "matches": [{"id": m.opportunity_id, "score": m.score, "barriers": m.barriers, "title": lookup[m.opportunity_id].title} for m in baseline if m.opportunity_id in selected]}
                output = invoke_agent("Fit", provider, context)
                if len(output.opportunity_ids) != len(selected) or set(output.opportunity_ids) != set(selected):
                    raise ValueError("Fit response changed the candidate set")
                selected = output.opportunity_ids
            positions = {i: n for n, i in enumerate(selected)}
            matches = sorted(baseline, key=lambda m: (0, positions[m.opportunity_id]) if m.opportunity_id in positions else (1, -m.score))
            return {"selected_ids": selected, "matches": matches}, "Prioritized candidates; published-rule results remain authoritative. Scores describe local relevance, never selection odds."
        return stage("Fit", work, {"matches": baseline}, state)

    graph = StateGraph(RunState)
    graph.add_node("discover", discovery)
    graph.add_node("evidence", evidence)
    graph.add_node("fit", fit)
    graph.add_edge(START, "discover")
    graph.add_edge("discover", "evidence")
    graph.add_edge("evidence", "fit")
    graph.add_edge("fit", END)
    result = graph.compile().invoke({"profile": profile, "records": catalog, "events": []})
    result["run_id"] = str(uuid4())
    return result


def application_tasks(record: Opportunity, provider: Fireworks | None = None) -> tuple[list[Task], AgentEvent]:
    started = perf_counter()
    indices = list(range(len(record.materials)))
    live = provider is not None and provider.ready
    status = "Complete"
    summary = "Prepared source-linked requirements and general preparation steps."
    if live and indices:
        try:
            output = invoke_agent("Planning", provider, {"title": record.title, "materials": record.materials})
            if len(output.material_indices) != len(indices) or set(output.material_indices) != set(indices):
                raise ValueError("Planning response changed requirements")
            indices = output.material_indices
        except Exception as error:
            status, summary = "Fallback", f"{type(error).__name__}: using source order and local checklist."
    tasks = [Task(id="verify", text="Recheck the current cycle, full eligibility, and official deadline.", kind="Suggested preparation", source_url=str(record.official_url))]
    tasks += [Task(id=f"material-{i}", text=record.materials[i], kind="Published material or process", source_url=str(next((c.url for c in record.claims if c.topic == "materials"), record.official_url))) for i in indices]
    tasks += [Task(id="costs", text="Ask the provider about upfront expenses, housing, payment timing, and any fee.", kind="Suggested preparation", source_url=str(record.official_url)),
              Task(id="review", text="Review your application and submit through the official provider portal.", kind="Suggested preparation", source_url=str(record.official_url))]
    return tasks, AgentEvent(stage="Planning", mode="Fireworks" if live and indices else "Local baseline", status=status, summary=summary, elapsed_ms=round((perf_counter()-started)*1000))
