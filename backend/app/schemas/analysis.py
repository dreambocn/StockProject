from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.schemas.stocks import StockDailySnapshotResponse, StockInstrumentResponse


class FactorWeightItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    factor_key: str
    factor_label: str
    weight: float
    direction: str
    evidence: list[str]
    reason: str


class AnalysisEventLinkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    event_id: str
    scope: str
    title: str
    published_at: datetime | None
    source: str
    macro_topic: str | None
    event_type: str | None
    event_tags: list[str]
    sentiment_label: str | None
    sentiment_score: float | None
    anchor_trade_date: date | None
    window_return_pct: float | None
    window_volatility: float | None
    abnormal_volume_ratio: float | None
    correlation_score: float | None
    confidence: str | None
    link_status: str | None


class AnalysisReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str | None = None
    status: Literal["ready", "partial", "pending"]
    summary: str
    risk_points: list[str]
    factor_breakdown: list[FactorWeightItemResponse]
    generated_at: datetime | None
    topic: str | None
    published_from: datetime | None
    published_to: datetime | None
    trigger_source: str = "manual"
    # used_web_search 标识是否实际调用检索能力，避免与开关混淆。
    used_web_search: bool = False
    web_search_status: Literal["used", "disabled", "unsupported"] = "disabled"
    session_id: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    content_format: Literal["markdown"] = "markdown"
    anchor_event_id: str | None = None
    anchor_event_title: str | None = None
    # structured_sources/web_sources 用于前端来源展示，允许为空数组。
    structured_sources: list[dict[str, object]] = []
    web_sources: list[dict[str, object]] = []


class AnalysisReportArchiveItemResponse(AnalysisReportResponse):
    pass


class AnalysisReportArchiveListResponse(BaseModel):
    ts_code: str
    items: list[AnalysisReportArchiveItemResponse]


class AnalysisSessionCreateRequest(BaseModel):
    topic: str | None = None
    event_id: str | None = None
    # force_refresh 为真时绕过缓存，强制重新生成。
    force_refresh: bool = False
    use_web_search: bool = False
    trigger_source: Literal["manual", "watchlist_daily"] = "manual"


class AnalysisSessionCreateResponse(BaseModel):
    session_id: str | None
    report_id: str | None = None
    status: str
    reused: bool = False
    cached: bool = False


class StockAnalysisSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ts_code: str
    instrument: StockInstrumentResponse | None
    latest_snapshot: StockDailySnapshotResponse | None
    status: Literal["ready", "partial", "pending"]
    generated_at: datetime | None
    topic: str | None
    # event_context_status 表示事件上下文获取口径，用于解释摘要来源。
    event_context_status: Literal["direct", "topic_fallback", "none"] = "none"
    event_context_message: str | None = None
    published_from: datetime | None
    published_to: datetime | None
    event_count: int
    events: list[AnalysisEventLinkResponse]
    report: AnalysisReportResponse | None
