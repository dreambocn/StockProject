from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class EvaluationDatasetResponse(BaseModel):
    model_config = ConfigDict(extra='ignore')

    id: str
    dataset_key: str
    label: str
    description: str | None = None
    sample_count: int
    date_from: date | None = None
    date_to: date | None = None


class EvaluationRunSummaryResponse(BaseModel):
    model_config = ConfigDict(extra='ignore')

    id: str
    run_key: str
    experiment_group_key: str
    variant_key: str
    variant_label: str
    prompt_profile_key: str
    model_name: str
    sample_count: int
    event_top1_hit_rate: float
    factor_top1_accuracy: float
    citation_metadata_completeness_rate: float
    avg_latency_ms: float
    created_at: datetime


class EvaluationExperimentGroupResponse(BaseModel):
    model_config = ConfigDict(extra='ignore')

    dataset_key: str
    experiment_group_key: str
    latest_baseline_run: EvaluationRunSummaryResponse | None = None
    latest_candidate_run: EvaluationRunSummaryResponse | None = None
    baseline_runs: list[EvaluationRunSummaryResponse] = []
    candidate_runs: list[EvaluationRunSummaryResponse] = []


class EvaluationCatalogResponse(BaseModel):
    datasets: list[EvaluationDatasetResponse]
    experiment_groups: list[EvaluationExperimentGroupResponse]


class EvaluationMetricCardResponse(BaseModel):
    metric_key: str
    label: str
    unit: str
    baseline_value: float
    candidate_value: float


class EvaluationBarChartResponse(BaseModel):
    categories: list[str]
    baseline_series: list[float]
    candidate_series: list[float]


class EvaluationDistributionChartResponse(BaseModel):
    improved: int
    unchanged: int
    regressed: int


class EvaluationCaseComparisonResponse(BaseModel):
    case_key: str
    ts_code: str
    topic: str | None = None
    anchor_event_title: str
    expected_top_factor_key: str
    notes: str | None = None
    baseline_score: float
    candidate_score: float
    score_delta: float
    classification: str
    baseline_top_event_title: str | None = None
    candidate_top_event_title: str | None = None
    baseline_top_factor_key: str | None = None
    candidate_top_factor_key: str | None = None
    baseline_citation_metadata_completeness_rate: float
    candidate_citation_metadata_completeness_rate: float
    baseline_latency_ms: float
    candidate_latency_ms: float


class EvaluationOverviewResponse(BaseModel):
    empty: bool
    dataset: EvaluationDatasetResponse | None = None
    experiment_group_key: str
    baseline_run: EvaluationRunSummaryResponse | None = None
    candidate_run: EvaluationRunSummaryResponse | None = None
    metric_cards: dict[str, EvaluationMetricCardResponse]
    bar_chart: EvaluationBarChartResponse
    distribution_chart: EvaluationDistributionChartResponse
    top_improved_cases: list[EvaluationCaseComparisonResponse]
    top_regressed_cases: list[EvaluationCaseComparisonResponse]
    recent_cases: list[EvaluationCaseComparisonResponse]


class EvaluationCaseLabelResponse(BaseModel):
    case_key: str
    ts_code: str
    topic: str | None = None
    anchor_event_title: str
    expected_top_factor_key: str
    notes: str | None = None


class EvaluationCaseResultResponse(BaseModel):
    event_top1_hit: bool
    factor_top1_hit: bool
    citation_metadata_completeness_rate: float
    latency_ms: float
    top_event_title: str | None = None
    top_factor_key: str | None = None
    web_source_count: int
    result_snapshot: dict[str, object] | None = None
    case_score: float
    classification: str


class EvaluationCaseDetailResponse(BaseModel):
    case: EvaluationCaseLabelResponse
    baseline_run: EvaluationRunSummaryResponse
    candidate_run: EvaluationRunSummaryResponse
    baseline_result: EvaluationCaseResultResponse
    candidate_result: EvaluationCaseResultResponse
