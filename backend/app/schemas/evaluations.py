from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


PromptProfile = Literal["production_current", "evidence_first_v2"]


class EvaluationCase(BaseModel):
    case_id: str
    dataset: str
    ts_code: str
    topic: str
    event_type: str
    case_tags: list[str] = Field(default_factory=list)
    expected_evidence_kinds: list[str] = Field(default_factory=list)
    expected_risk_keywords: list[str] = Field(default_factory=list)
    baseline_context: str


class EvaluationDatasetOption(BaseModel):
    dataset: str
    title: str
    case_count: int
    event_types: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    case_tags: list[str] = Field(default_factory=list)


class EvaluationMetricBreakdown(BaseModel):
    citation_completeness: float
    evidence_coverage: float
    risk_notice_coverage: float
    conclusion_stability: float
    failure_rate: float


class EvaluationRunSummary(BaseModel):
    total_cases: int
    profiles: list[str]
    metric_breakdown: dict[str, EvaluationMetricBreakdown]


class EvaluationCaseResult(BaseModel):
    case_id: str
    dataset: str
    ts_code: str
    topic: str
    event_type: str
    case_tags: list[str]
    prompt_profile: str
    conclusion: str
    citations: list[str] = Field(default_factory=list)
    evidence_kinds: list[str] = Field(default_factory=list)
    risk_notices: list[str] = Field(default_factory=list)
    metric_breakdown: EvaluationMetricBreakdown
    failure_reason: str | None = None


class EvaluationRun(BaseModel):
    run_id: str
    dataset: str
    profiles: list[str]
    status: Literal["success", "partial", "failed"]
    started_at: datetime
    completed_at: datetime | None = None
    duration_ms: int | None = None
    runtime_metadata: dict[str, object] = Field(default_factory=dict)
    summary: EvaluationRunSummary
    case_results: list[EvaluationCaseResult] = Field(default_factory=list)


class EvaluationRunListItem(BaseModel):
    run_id: str
    dataset: str
    profiles: list[str]
    status: Literal["success", "partial", "failed"]
    started_at: datetime
    completed_at: datetime | None = None
    duration_ms: int | None = None
    runtime_metadata: dict[str, object] = Field(default_factory=dict)
    summary: EvaluationRunSummary


class EvaluationRunRequest(BaseModel):
    dataset: str = "default_research_cases"
    profiles: list[PromptProfile] = Field(
        default_factory=lambda: ["production_current", "evidence_first_v2"]
    )
