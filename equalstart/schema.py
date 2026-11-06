from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Profile(StrictModel):
    goal: str = Field(min_length=3, max_length=1200)
    discipline: str = "Environment"
    year: str | None = "Sophomore"
    institution_type: str | None = "Four-year"
    institution: str | None = None
    citizenship: str | None = None
    gpa: float | None = Field(default=None, ge=0, le=4)
    full_time: bool | None = None
    research_career: bool | None = None
    transfer_plans: bool | None = None
    no_upfront: bool = True
    needs_housing: bool = True


class Claim(StrictModel):
    id: str
    topic: Literal["overview", "eligibility", "funding", "timing", "materials"]
    text: str = Field(min_length=1, max_length=900)
    url: HttpUrl
    checked: date


class Rule(StrictModel):
    field: Literal["year", "institution_type", "institution", "citizenship", "gpa", "full_time", "research_career", "transfer_plans", "discipline"]
    op: Literal["in", "gte", "eq"]
    value: Any
    label: str
    claim_id: str


class Opportunity(StrictModel):
    id: str = Field(pattern=r"^[a-z0-9-]+$")
    title: str
    provider: str
    category: Literal["Scholarship", "Research", "Internship"]
    summary: str
    location: str
    country: Literal["US"] = "US"
    tags: list[str]
    award: str
    housing: Literal["Provided", "Allowance or arranged", "Not provided", "Unknown"] = "Unknown"
    travel: Literal["Supported; timing unknown", "Reimbursed", "Unknown"] = "Unknown"
    fee: str = "Not confirmed"
    upfront: Literal["Unknown", "Reimbursement barrier", "Confirmed none"] = "Unknown"
    opens_on: date | None = None
    deadline: datetime | None = None
    deadline_date: date | None = None
    cycle: str
    cycle_status: Literal["Open", "Upcoming", "Closed", "Unknown"] = "Unknown"
    official_url: HttpUrl
    claims: list[Claim]
    rules: list[Rule] = Field(default_factory=list)
    confirmations: list[str] = Field(default_factory=list)
    materials: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def evidence_links(self):
        ids = [c.id for c in self.claims]
        if len(ids) != len(set(ids)) or not ids:
            raise ValueError("Each record needs uniquely identified evidence")
        if any(r.claim_id not in ids for r in self.rules):
            raise ValueError("Every rule must reference evidence")
        if self.deadline is not None and self.deadline.tzinfo is None:
            raise ValueError("A precise deadline must include its timezone")
        return self


class Criterion(StrictModel):
    label: str
    state: Literal["Met", "Not met", "Unknown"]
    detail: str
    claim_id: str | None = None


class Match(StrictModel):
    opportunity_id: str
    status: Literal["Screened criteria met", "Needs confirmation", "Not eligible"]
    score: int
    components: dict[str, int]
    criteria: list[Criterion]
    barriers: list[str]
    cycle_status: str


class AgentEvent(StrictModel):
    stage: str
    mode: str
    status: str
    summary: str
    elapsed_ms: int


class DiscoveryOutput(StrictModel):
    opportunity_ids: list[str] = Field(max_length=12)


class EvidenceOutput(StrictModel):
    unconfirmed_claim_ids: list[str] = Field(max_length=80)


class FitOutput(StrictModel):
    opportunity_ids: list[str] = Field(max_length=12)


class PlanningOutput(StrictModel):
    material_indices: list[int] = Field(max_length=20)


class Task(StrictModel):
    id: str
    text: str
    kind: str
    source_url: str | None = None
    depends_on: list[str] = Field(default_factory=list)
    suggested_date: date | None = None
    effort: str = "Confirm effort"
    external_help: bool = False


class SourceSnapshot(StrictModel):
    id: str
    opportunity_id: str
    url: HttpUrl
    retrieved_at: datetime
    content: str = Field(max_length=16000)


class GroundedFinding(StrictModel):
    claim_id: str
    snapshot_id: str
    status: Literal["Supported", "Contradicted", "Not found"]
    quote: str = Field(default="", max_length=1800)
    passage_index: int | None = Field(default=None, ge=0)


class GroundedEvidenceOutput(StrictModel):
    findings: list[GroundedFinding] = Field(max_length=30)


class ResearchAction(StrictModel):
    action: Literal["search", "fetch", "clarify", "finish"]
    opportunity_id: str = ""
