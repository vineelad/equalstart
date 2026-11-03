import re
from datetime import datetime
from zoneinfo import ZoneInfo

from equalstart.schema import Criterion, Match, Opportunity, Profile


def local_now() -> datetime:
    return datetime.now(ZoneInfo("America/Chicago"))


def cycle_status(record: Opportunity, now: datetime | None = None) -> str:
    now = now or local_now()
    if record.deadline and now > record.deadline:
        return "Closed"
    if record.deadline_date:
        if now.date() > record.deadline_date:
            return "Closed"
        if now.date() == record.deadline_date:
            return "Confirm closing time"
    if record.opens_on and now.date() < record.opens_on:
        return "Upcoming"
    if record.cycle_status == "Upcoming" and record.opens_on and now.date() >= record.opens_on:
        return "Open" if record.deadline or record.deadline_date else "Unknown"
    return record.cycle_status


def assess(profile: Profile, record: Opportunity, now: datetime | None = None) -> Match:
    criteria = []
    for rule in record.rules:
        value = getattr(profile, rule.field)
        state = "Unknown"
        if value is not None:
            if rule.op == "in":
                passed = value in rule.value
            elif rule.op == "gte":
                passed = value >= rule.value
            elif isinstance(value, str) and isinstance(rule.value, str):
                passed = " ".join(value.casefold().split()) == " ".join(rule.value.casefold().split())
            else:
                passed = value == rule.value
            state = "Met" if passed else "Not met"
        criteria.append(Criterion(label=rule.label, state=state, detail="Profile matches this recorded rule." if state == "Met" else "Your profile does not meet this rule." if state == "Not met" else "Add this profile detail or confirm with the provider.", claim_id=rule.claim_id))
    criteria.extend(Criterion(label=x, state="Unknown", detail="Confirm this additional condition using the official source.") for x in record.confirmations)
    state = "Not eligible" if any(c.state == "Not met" for c in criteria) else "Needs confirmation" if any(c.state == "Unknown" for c in criteria) else "Screened criteria met"
    barriers = []
    if profile.no_upfront:
        if record.upfront == "Reimbursement barrier":
            barriers.append("Travel is reimbursed: ask about an advance before committing.")
        elif record.upfront != "Confirmed none":
            barriers.append("Upfront expenses and payment timing need confirmation.")
    if profile.needs_housing and record.category != "Scholarship":
        if record.housing == "Not provided":
            barriers.append("Housing is not provided; a separate housing plan is needed.")
        elif record.housing in ("Unknown", "Allowance or arranged"):
            barriers.append("Confirm housing availability and any gap in its cost.")
    goal_words = set(re.findall(r"[a-z]{3,}", profile.goal.lower()))
    searchable = set(re.findall(r"[a-z]{3,}", (record.title + " " + record.summary + " " + " ".join(record.tags)).lower()))
    overlap = len(goal_words & searchable)
    discipline_fit = profile.discipline in record.tags or "All fields" in record.tags
    goal_fit = min(40, (25 if discipline_fit else 5) + overlap * 5)
    funding = (0 if "not confirmed" in record.award.lower() else 20) + (10 if record.housing == "Provided" else 5 if record.housing == "Allowance or arranged" else 0)
    funding = max(0, min(30, funding - 5 * len(barriers)))
    known = sum(c.state == "Met" for c in criteria)
    feasibility = round(20 * known / max(1, len(criteria)))
    preferences = 10 if not barriers else 3
    components = {"Goal fit": goal_fit, "Funding evidence": funding, "Known criteria": feasibility, "Constraints": preferences}
    return Match(opportunity_id=record.id, status=state, score=sum(components.values()), components=components, criteria=criteria, barriers=barriers, cycle_status=cycle_status(record, now))


def rank(profile: Profile, catalog: list[Opportunity], now: datetime | None = None) -> list[Match]:
    return sorted((assess(profile, r, now) for r in catalog), key=lambda m: (m.status != "Not eligible", m.cycle_status != "Closed", m.score), reverse=True)
