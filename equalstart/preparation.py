"""Conservative dependency planning and editable drafts; no external side effects."""
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


def prerequisite_order(materials):
    """A deterministic fallback for explicit external requests and submissions."""
    def weight(text):
        text = text.lower()
        if re.search(r"contact|request|ask |verify|check .*eligib", text):
            return 0
        if re.search(r"receive|obtain|collect|prepare|write|draft", text):
            return 1
        if re.search(r"upload|attach", text):
            return 2
        if re.search(r"submit|submission", text):
            return 4
        return 2
    return sorted(range(len(materials)), key=lambda i: (weight(materials[i]), i))


def enrich_tasks(tasks, record, today=None):
    """Sequence suggestions, not invented provider requirements or deadlines."""
    today = today or datetime.now(ZoneInfo("America/Chicago")).date()
    deadline = record.deadline.date() if record.deadline else record.deadline_date
    days = (deadline-today).days if deadline else None
    valid_window = days is not None and days >= 0
    output = []
    for index, task in enumerate(tasks):
        text = task.text.lower()
        external = bool(re.search(r"reference|recommend|nomina|provider|representative", text))
        effort = "Allow another person time to respond" if external else "Set aside one preparation session"
        # Scheduling dates are suggestions, never newly asserted provider dates.
        suggested = today + timedelta(days=(index*max(0, days-1)//max(1, len(tasks)-1))) if valid_window else None
        dependencies = [] if task.id == "verify" else ["verify"]
        if re.search(r"submit|submission", text) and task.id != "review":
            dependencies += [item.id for item in output if item.id != "verify"]
        elif re.search(r"receive|attach|upload", text):
            dependencies += [item.id for item in output if re.search(r"request|obtain|collect|prepare", item.text.lower()) and item.id.startswith("material-")]
        output.append(task.model_copy(update={"depends_on": list(dict.fromkeys(dependencies)),
                                              "suggested_date": suggested, "effort": effort, "external_help": external}))
    validate_dependencies(output)
    return output


def validate_dependencies(tasks):
    ids = [task.id for task in tasks]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate task IDs")
    seen = set()
    for task in tasks:
        if any(dep not in seen for dep in task.depends_on):
            raise ValueError("Dependency is missing, cyclic or ordered after its task")
        seen.add(task.id)


def outreach_drafts(record):
    source = str(record.official_url)
    return {
        "Funding questions": f"Hello,\n\nI am considering {record.title}. Could you confirm the current cycle, full eligibility requirements, and application deadline?\n\nI also need to understand whether travel or other expenses must be paid before reimbursement, whether an advance is available, and what housing support covers.\n\nI reviewed: {source}\n\nThank you,\n[Your name]",
        "Reference request": f"Hello [name],\n\nI am preparing an application for {record.title} and would like to ask whether you could provide a reference if the current application requires one. I can share my interests, relevant work, and the official instructions.\n\nCould you let me know whether this is something you can support? I will confirm the provider's deadline and your available time before making arrangements.\n\nOpportunity: {source}\n\nThank you,\n[Your name]",
        "Nomination or support route": f"Hello,\n\nI am interested in {record.title} and do not yet have an established contact for application support. Does this program require institutional nomination or specific references? If so, could you point me to the published process or appropriate representative?\n\nOfficial information reviewed: {source}\n\nThank you,\n[Your name]",
    }
