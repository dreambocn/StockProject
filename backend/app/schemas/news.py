from datetime import datetime

from pydantic import BaseModel


class HotNewsItemResponse(BaseModel):
    # providers/source_coverage 用于展示多来源覆盖情况。
    event_id: str | None = None
    cluster_key: str | None = None
    providers: list[str] = []
    source_coverage: str = "AK"
    title: str
    summary: str | None
    published_at: datetime | None
    url: str | None
    source: str
    macro_topic: str


class StockRelatedNewsItemResponse(BaseModel):
    ts_code: str
    symbol: str
    title: str
    summary: str | None
    published_at: datetime | None
    url: str | None
    publisher: str | None
    source: str


class CandidateEvidenceItemResponse(BaseModel):
    ts_code: str
    symbol: str
    name: str
    evidence_kind: str
    title: str
    summary: str | None
    published_at: datetime | None
    url: str | None
    source: str


class CandidateEvidenceSourceBreakdownResponse(BaseModel):
    source: str
    count: int


class CandidateEvidenceSummaryResponse(BaseModel):
    ts_code: str
    hot_search_count: int = 0
    research_report_count: int = 0
    latest_published_at: datetime | None = None
    # source_breakdown 用于展示证据来源占比。
    source_breakdown: list[CandidateEvidenceSourceBreakdownResponse] = []
    evidence_items: list[CandidateEvidenceItemResponse] = []


class MacroImpactCandidateResponse(BaseModel):
    ts_code: str
    symbol: str
    name: str
    industry: str | None
    relevance_score: int = 0
    match_reasons: list[str] = []
    evidence_summary: str = ""
    source_hit_count: int = 0
    source_breakdown: list[CandidateEvidenceSourceBreakdownResponse] = []
    freshness_score: int = 0
    candidate_confidence: str = "低"
    # evidence_items 仅返回必要条目，避免列表过大。
    evidence_items: list[CandidateEvidenceItemResponse] = []


class AnchorEventResponse(BaseModel):
    event_id: str | None = None
    title: str
    published_at: datetime | None
    providers: list[str] = []
    source_coverage: str = "AK"


class MacroImpactProfileResponse(BaseModel):
    topic: str
    affected_assets: list[str]
    beneficiary_sectors: list[str]
    pressure_sectors: list[str]
    a_share_targets: list[str]
    anchor_event: AnchorEventResponse | None = None
    a_share_candidates: list[MacroImpactCandidateResponse]


class NewsEventResponse(BaseModel):
    scope: str
    cache_variant: str
    ts_code: str | None
    symbol: str | None
    title: str
    summary: str | None
    published_at: datetime | None
    url: str | None
    publisher: str | None
    source: str
    macro_topic: str | None
    fetched_at: datetime
