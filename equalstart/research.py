"""Bounded research with validated actions, official source receipts and no profile storage."""
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from time import perf_counter
from typing import TypedDict
from urllib.parse import urlparse

from langgraph.graph import END, START, StateGraph

from equalstart.agents import invoke_agent
from equalstart.schema import ResearchAction, SourceSnapshot


class ResearchState(TypedDict, total=False):
    action: str
    target: str
    snapshots: list[SourceSnapshot]
    trace: list[dict]
    attempted: list[str]
    searches: int
    rounds: int
    clarification: dict | None
    leads: list[dict]
    stop_reason: str


QUESTIONS = {
    "citizenship": ("Which citizenship or residency category should we use to check the recorded requirements?", ["US citizen", "US national", "Permanent resident", "DACA", "International student", "Other"]),
    "institution_type": ("Are you attending a community college or a four-year institution?", ["Community college", "Four-year"]),
    "year": ("What is your current undergraduate year?", ["Freshman", "Sophomore", "Junior", "Senior"]),
    "full_time": ("Are you enrolled full time?", ["Yes", "No"]),
    "transfer_plans": ("Are you planning to transfer from community college?", ["Yes", "No"]),
    "research_career": ("Are you interested in pursuing a research career?", ["Yes", "No"]),
}


def clarification_for(profile, records):
    """Ask only about a missing field actually used by a candidate's rules."""
    fields = {rule.field for record in records for rule in record.rules}
    for field, (prompt, options) in QUESTIONS.items():
        if field in fields and getattr(profile, field) is None:
            return {"field": field, "prompt": prompt, "options": options}
    return None


def snapshot_from(record, url, content, retrieved_at):
    if not isinstance(content, str) or not content.strip():
        raise ValueError("Source returned no usable text")
    parsed = urlparse(url)
    approved = {str(record.official_url), *(str(claim.url) for claim in record.claims)}
    if url not in approved or parsed.scheme != "https" or parsed.username or parsed.password:
        raise ValueError("Source is not a reviewed provider URL")
    content = content[:16000]
    fingerprint = hashlib.sha256(f"{record.id}:{url}:{content}".encode()).hexdigest()[:20]
    return SourceSnapshot(id=f"source-{fingerprint}", opportunity_id=record.id, url=url,
                          retrieved_at=retrieved_at, content=content)


def retrieve_source(record, client, store=None, now=None, source_url=None):
    now = now or datetime.now(timezone.utc)
    url = source_url or str(record.official_url)
    approved = {str(record.official_url), *(str(claim.url) for claim in record.claims)}
    if url not in approved:
        raise ValueError("Fetch URL is outside the reviewed source set")
    cached = store.source(url) if store else None
    # Import an existing official source receipt without introducing another fetch.
    if cached is None and store and url == str(record.official_url):
        receipt = store.path.parent / "source-review" / f"{record.id}.json"
        if receipt.is_file():
            try:
                value = json.loads(receipt.read_text(encoding="utf-8"))
                if value.get("url") == url:
                    cached = snapshot_from(record, url, value["content"], datetime.fromisoformat(value["fetched_at"])).model_dump(mode="json")
            except (ValueError, TypeError, KeyError):
                pass
    if cached:
        try:
            snapshot = SourceSnapshot.model_validate(cached)
            age = now - snapshot.retrieved_at
            if str(snapshot.url) == url and timedelta(0) <= age <= timedelta(hours=6):
                rebound = snapshot_from(record, url, snapshot.content, snapshot.retrieved_at)
                if store:
                    store.save_source(rebound.model_dump(mode="json"))
                return rebound, "Cached source"
        except (ValueError, TypeError):
            pass
    if client is None:
        raise RuntimeError("Live source retrieval unavailable; cached evidence is absent or stale")
    page = client.fetch(url, {urlparse(url).hostname})
    snapshot = snapshot_from(record, url, page.get("content", ""), now)
    if store:
        store.save_source(snapshot.model_dump(mode="json"))
    return snapshot, "Fetched source"


def source_context(snapshot, claims, limit=6500):
    """Select relevant exact paragraphs; do not synthesize evidence text."""
    paragraphs = [x.strip() for x in re.split(r"\n\s*\n|\n", snapshot.content) if x.strip()]
    terms = set(re.findall(r"[a-z0-9]{3,}", " ".join(c.text for c in claims).lower()))
    ranked = sorted(enumerate(paragraphs), key=lambda item: -len(set(re.findall(r"[a-z0-9]{3,}", item[1].lower())) & terms))
    chosen, size = [], 0
    for index, paragraph in ranked:
        paragraph = paragraph[:2200]
        if size + len(paragraph) > limit:
            continue
        chosen.append((index, paragraph))
        size += len(paragraph) + 2
    content = "\n\n".join(value for _, value in sorted(chosen))
    return {"id": snapshot.id, "opportunity_id": snapshot.opportunity_id, "url": str(snapshot.url), "content": content}


def research_sources(profile, records, provider=None, client=None, store=None,
                     allow_clarification=True, search_already_attempted=False, now=None, max_fetches=3):
    # This scope never grows from unreviewed search results.
    lookup = {record.id: record for record in records[:3]}
    question = clarification_for(profile, list(lookup.values())) if allow_clarification else None
    live = bool(provider and provider.ready)

    def choose(state):
        fetchable = [rid for rid in lookup if rid not in state["attempted"]]
        available = ["finish"]
        if fetchable and len(state["attempted"]) < max_fetches and client is not None:
            available.append("fetch")
        if client is not None and state["searches"] < 2:
            available.append("search")
        if question:
            available.append("clarify")
        if state["rounds"] >= 6 or state["clarification"]:
            return {"action": "finish", "stop_reason": "Research limit reached" if not state["clarification"] else "Optional clarification offered"}
        if not lookup and state["searches"] > 0:
            return {"action": "finish", "stop_reason": "No reviewed candidate to investigate; leads require review"}
        # Completed sources do not justify more model/tool calls by themselves.
        if not fetchable and not question:
            return {"action": "finish", "stop_reason": "Approved candidate research completed"}
        if len(state["attempted"]) >= max_fetches and not question:
            return {"action": "finish", "stop_reason": "Initial source limit reached; evidence review may use one remaining fetch"}
        default = ResearchAction(action="clarify") if question else ResearchAction(action="fetch", opportunity_id=fetchable[0]) if "fetch" in available else ResearchAction(action="finish")
        mode, reason = "Local controller", "Validated bounded action"
        started = perf_counter()
        if live and len(available) > 1:
            try:
                default = invoke_agent("Discovery", provider, {"goal": profile.goal, "research_state": {
                    "available_actions": available, "fetchable_ids": fetchable,
                    "clarification_available": bool(question), "missing_field": question["field"] if question else None,
                    "completed_sources": len(state["snapshots"]), "remaining_fetches": max_fetches-len(state["attempted"]),
                    "remaining_searches": 2-state["searches"],
                }})
                mode = "Fireworks"
            except Exception as error:
                mode, reason = "Fallback", f"{type(error).__name__}: local bounded action retained"
        trace = state["trace"] + [{"action": default.action, "opportunity_id": default.opportunity_id,
                                  "status": "Chosen", "mode": mode, "reason": reason,
                                  "elapsed_ms": round((perf_counter()-started)*1000)}]
        return {"action": default.action, "target": default.opportunity_id, "rounds": state["rounds"]+1,
                "trace": trace, "stop_reason": "Agent finished research" if default.action == "finish" else ""}

    def fetch(state):
        rid = state["target"]
        started = perf_counter()
        entry = {"action": "fetch", "opportunity_id": rid, "mode": "Keenable", "status": "Unavailable"}
        snapshots = state["snapshots"]
        try:
            snapshot, status = retrieve_source(lookup[rid], client, store, now)
            snapshots = snapshots + [snapshot]
            entry.update(status=status, source_id=snapshot.id)
        except Exception as error:
            entry["reason"] = f"{type(error).__name__}: source remains unverified"
        entry["elapsed_ms"] = round((perf_counter()-started)*1000)
        return {"snapshots": snapshots, "attempted": state["attempted"]+[rid], "trace": state["trace"]+[entry]}

    def search(state):
        started = perf_counter()
        entry = {"action": "search", "mode": "Keenable", "status": "Complete"}
        leads = state["leads"]
        try:
            leads = leads + client.search(f"undergraduate {profile.discipline} scholarships funded research USA")
        except Exception as error:
            entry.update(status="Unavailable", reason=f"{type(error).__name__}: reviewed catalog retained")
        entry["elapsed_ms"] = round((perf_counter()-started)*1000)
        return {"searches": state["searches"]+1, "leads": leads[:10], "trace": state["trace"]+[entry]}

    def clarify(state):
        return {"clarification": question, "stop_reason": "Optional clarification offered"}

    graph = StateGraph(ResearchState)
    graph.add_node("choose", choose)
    graph.add_node("fetch", fetch)
    graph.add_node("search", search)
    graph.add_node("clarify", clarify)
    graph.add_edge(START, "choose")
    graph.add_conditional_edges("choose", lambda state: state["action"], {"fetch": "fetch", "search": "search", "clarify": "clarify", "finish": END})
    graph.add_edge("fetch", "choose")
    graph.add_edge("search", "choose")
    graph.add_edge("clarify", END)
    result = graph.compile().invoke({"snapshots": [], "trace": [], "attempted": [], "searches": int(search_already_attempted),
                                     "rounds": 0, "clarification": None, "leads": [], "stop_reason": ""})
    return result
