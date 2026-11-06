"""Student-facing decisions rendered from existing rules and cited findings."""


def readiness(record, match, findings=()):
    relevant = [finding for finding in findings if finding["claim_id"] in {c.id for c in record.claims}]
    unresolved = [finding for finding in relevant if finding["status"] != "Supported"]
    if match.status == "Not eligible":
        label, next_step = "Known restriction", "Review the recorded requirement that is not met."
    elif match.cycle_status == "Closed":
        label, next_step = "Cycle closed", "Check the provider for a future cycle."
    elif match.cycle_status == "Upcoming":
        label, next_step = "Watch next cycle", "Confirm opening dates and prepare external requests."
    elif unresolved or match.status == "Needs confirmation" or match.barriers or match.cycle_status != "Open":
        label, next_step = "Confirm conditions", "Resolve the eligibility, evidence or cost questions before committing."
    else:
        label, next_step = "Start preparation", "Recheck the official cycle and start the published materials."
    topics = sorted({c.topic for c in record.claims if c.id in {f["claim_id"] for f in unresolved}})
    return {"label": label, "next_step": next_step, "supported": sum(f["status"] == "Supported" for f in relevant),
            "unresolved": len(unresolved), "topics": topics,
            "evidence": "Retrieved passages assessed" if relevant else "Reviewed catalog only; fresh support not assessed"}
