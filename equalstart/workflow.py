from datetime import datetime
import re
from time import perf_counter
from typing import TypedDict
from uuid import uuid4

from langgraph.graph import END, START, StateGraph

from equalstart.eligibility import rank
from equalstart.agents import invoke_agent
from equalstart.providers import Fireworks, Keenable, provider_display_name
from equalstart.schema import AgentEvent, Match, Opportunity, Profile, Task
from equalstart.research import research_sources, source_context, retrieve_source
from equalstart.preparation import enrich_tasks


class RunState(TypedDict, total=False):
    profile: Profile
    records: list[Opportunity]
    matches: list[Match]
    selected_ids: list[str]
    events: list[AgentEvent]
    flagged_claims: list[str]
    leads: list[dict]
    snapshots: list
    research_trace: list[dict]
    clarification: dict | None
    findings: list[dict]
    stop_reason: str
    evidence_retry_done: bool
    followup_has_source: bool
    research_fetches: int


def run_matching(profile: Profile, catalog: list[Opportunity], provider: Fireworks | None = None, now: datetime | None = None, search: Keenable | None = None, store=None, allow_clarification=True) -> RunState:
    baseline = rank(profile, catalog, now)
    live = provider is not None and provider.ready
    provider_label = provider_display_name(provider)

    def stage(name, function, fallback, state):
        started = perf_counter()
        requested_model = live and bool(initial if name == "Discovery" else state.get("selected_ids", []))
        actual_mode = provider_label if requested_model else "Local baseline"
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
            sources = state.get("snapshots", [])
            findings = []
            if sources:
                source_ids = {source.opportunity_id for source in sources}
                claims = [{**c.model_dump(mode="json"), "opportunity_id": rid} for rid in state["selected_ids"] if rid in source_ids for c in lookup[rid].claims]
                context = {"claims": claims, "sources": [source_context(source, lookup[source.opportunity_id].claims) for source in sources]}
                if live:
                    output = invoke_agent("Evidence", provider, context)
                    findings = [finding.model_dump() for finding in output.findings]
                else:
                    findings = [{"claim_id": claim["id"], "snapshot_id": next(s.id for s in sources if s.opportunity_id == claim["opportunity_id"]),
                                 "status": "Not assessed", "quote": ""} for claim in claims]
                flagged = [finding["claim_id"] for finding in findings if finding["status"] != "Supported"]
                return {"findings": findings, "flagged_claims": flagged}, f"Assessed {len(findings)} claims against retrieved passages; {len(flagged)} require confirmation. Quotes are localized evidence, not an eligibility guarantee."
            claims = [c.model_dump(mode="json") for i in state["selected_ids"] for c in lookup[i].claims]
            flagged = []
            if live and claims:
                output = invoke_agent("Evidence", provider, {"claims": claims})
                if not set(output.unconfirmed_claim_ids).issubset({c["id"] for c in claims}):
                    raise ValueError("Unknown evidence reference")
                flagged = output.unconfirmed_claim_ids
            return {"flagged_claims": flagged, "findings": []}, f"Inspected {len(claims)} stored evidence references; {len(flagged)} flagged for review. No live re-verification implied."
        source_by_record = {source.opportunity_id:source for source in state.get("snapshots", [])}
        fallback_findings = [{"claim_id": c.id, "snapshot_id": source.id, "status": "Not assessed", "quote": ""}
                             for source in source_by_record.values() for c in lookup[source.opportunity_id].claims]
        return stage("Evidence", work, {"flagged_claims": [f["claim_id"] for f in fallback_findings], "findings": fallback_findings}, state)

    def research(state):
        result = research_sources(profile, [lookup[rid] for rid in state["selected_ids"][:3]],
                                  provider if live else None, search, store,
                                  allow_clarification=allow_clarification, search_already_attempted=search is not None, now=now, max_fetches=2)
        return {"snapshots": result["snapshots"], "research_trace": result["trace"], "clarification": result["clarification"],
                "stop_reason": result["stop_reason"], "leads": state.get("leads", [])+result["leads"],
                "research_fetches": len(result["attempted"]), "evidence_retry_done": False}

    def followup_targets(state):
        if state.get("evidence_retry_done") or not live or search is None or state.get("research_fetches", 0) >= 3:
            return {}
        visited = {str(source.url) for source in state.get("snapshots", [])}
        missing = {finding["claim_id"] for finding in state.get("findings", []) if finding["status"] in ("Not found", "Not assessed")}
        return {rid:str(claim.url) for rid in state["selected_ids"] for claim in lookup[rid].claims
                if claim.id in missing and claim.topic in ("funding", "timing", "eligibility") and str(claim.url) not in visited}

    def evidence_followup(state):
        targets = followup_targets(state)
        trace = {"action":"evidence-followup", "mode":provider_label, "status":"Not fetched", "reason":"Missing decisive source evidence"}
        snapshots = state.get("snapshots", [])
        started = perf_counter()
        fetched = False
        attempted = 0
        try:
            action = invoke_agent("Discovery", provider, {"goal":profile.goal, "research_state":{
                "available_actions":["fetch","finish"], "fetchable_ids":list(targets), "clarification_available":False,
                "completed_sources":len(snapshots), "remaining_fetches":1, "remaining_searches":0,
                "evidence_gap":"Missing funding, timing or eligibility passage; an additional reviewed URL is available."}})
            if action.action == "fetch":
                attempted = 1
                snapshot, status = retrieve_source(lookup[action.opportunity_id], search, store, now,
                                                   source_url=targets[action.opportunity_id])
                snapshots = snapshots+[snapshot]
                fetched = True
                trace.update(opportunity_id=action.opportunity_id, source_id=snapshot.id, status=status)
            else:
                trace["reason"] = "Agent stopped rather than pursue another source"
        except Exception as error:
            trace.update(status="Unavailable", reason=f"{type(error).__name__}: evidence remains unresolved")
        trace["elapsed_ms"] = round((perf_counter()-started)*1000)
        return {"evidence_retry_done":True, "followup_has_source":fetched, "snapshots":snapshots,
                "research_fetches":state.get("research_fetches",0)+attempted,
                "research_trace":state.get("research_trace",[])+[trace],
                "stop_reason":"One evidence-driven follow-up completed; unresolved conditions still need confirmation"}

    def fit(state):
        def work():
            selected = state["selected_ids"]
            if live and selected:
                flagged = set(state.get("flagged_claims", []))
                context = {"goal": profile.goal, "no_upfront": profile.no_upfront, "needs_housing": profile.needs_housing,
                           "matches": [{"id": m.opportunity_id, "score": m.score, "barriers": m.barriers,
                                        "evidence_needs_confirmation": [c.topic for c in lookup[m.opportunity_id].claims if c.id in flagged],
                                        "fresh_evidence_status": "Assessed with unresolved claims" if any(c.id in flagged for c in lookup[m.opportunity_id].claims) else "Assessed" if any(f["claim_id"] in {c.id for c in lookup[m.opportunity_id].claims} for f in state.get("findings", [])) else "Not assessed",
                                        "title": lookup[m.opportunity_id].title} for m in baseline if m.opportunity_id in selected]}
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
    graph.add_node("research", research)
    graph.add_node("evidence", evidence)
    graph.add_node("evidence_followup", evidence_followup)
    graph.add_node("fit", fit)
    graph.add_edge(START, "discover")
    graph.add_edge("discover", "research")
    graph.add_edge("research", "evidence")
    graph.add_conditional_edges("evidence", lambda state:"evidence_followup" if followup_targets(state) else "fit",
                                {"evidence_followup":"evidence_followup", "fit":"fit"})
    graph.add_conditional_edges("evidence_followup", lambda state:"evidence" if state["followup_has_source"] else "fit",
                                {"evidence":"evidence", "fit":"fit"})
    graph.add_edge("fit", END)
    result = graph.compile().invoke({"profile": profile, "records": catalog, "events": []})
    result["run_id"] = str(uuid4())
    if store:
        store.log_research(result["run_id"], result.get("research_trace", []))
    return result


def application_tasks(record: Opportunity, provider: Fireworks | None = None, today=None) -> tuple[list[Task], AgentEvent]:
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
    tasks = [Task(id="verify", text="Recheck the current cycle, full eligibility, and official deadline.", kind="Suggested preparation", source_url=str(record.official_url)),
             Task(id="costs", text="Ask the provider about upfront expenses, housing, payment timing, and any fee.", kind="Suggested preparation", source_url=str(record.official_url))]
    tasks += [Task(id=f"material-{i}", text=record.materials[i], kind="Published material or process", source_url=str(next((c.url for c in record.claims if c.topic == "materials"), record.official_url))) for i in indices]
    review = Task(id="review", text="Review your application before submitting through the official provider portal.", kind="Suggested preparation", source_url=str(record.official_url))
    submission = next((n for n, task in enumerate(tasks) if task.id.startswith("material-") and re.search(r"\bsubmit\b|final submission", task.text.lower())), len(tasks))
    tasks.insert(submission, review)
    return enrich_tasks(tasks, record, today), AgentEvent(stage="Planning", mode=provider_display_name(provider) if live and indices else "Local baseline", status=status, summary=summary, elapsed_ms=round((perf_counter()-started)*1000))
