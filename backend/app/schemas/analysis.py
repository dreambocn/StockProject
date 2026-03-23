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

    status: Literal["ready", "partial", "pending"]
    summary: str
    risk_points: list[str]
    factor_breakdown: list[FactorWeightItemResponse]
    generated_at: datetime | None
    topic: str | None
    published_from: datetime | None
    published_to: datetime | None


class StockAnalysisSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ts_code: str
    instrument: StockInstrumentResponse | None
    latest_snapshot: StockDailySnapshotResponse | None
    status: Literal["ready", "partial", "pending"]
    generated_at: datetime | None
    topic: str | None
    published_from: datetime | None
    published_to: datetime | None
    event_count: int
    events: list[AnalysisEventLinkResponse]
    report: AnalysisReportResponse | None
