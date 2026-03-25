from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.analysis import AnalysisReportArchiveItemResponse
from app.schemas.stocks import StockInstrumentResponse


class WatchlistItemCreateRequest(BaseModel):
    ts_code: str = Field(min_length=6, max_length=12)
    # 默认开启同步与分析，保持新增订阅即可生效的体验。
    hourly_sync_enabled: bool = True
    daily_analysis_enabled: bool = True
    web_search_enabled: bool = False


class WatchlistItemUpdateRequest(BaseModel):
    # 允许局部更新，None 表示不修改。
    hourly_sync_enabled: bool | None = None
    daily_analysis_enabled: bool | None = None
    web_search_enabled: bool | None = None


class WatchlistItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    ts_code: str
    hourly_sync_enabled: bool
    daily_analysis_enabled: bool
    web_search_enabled: bool
    last_hourly_sync_at: datetime | None
    last_daily_analysis_at: datetime | None
    created_at: datetime
    updated_at: datetime
    instrument: StockInstrumentResponse | None = None
    # latest_report 可能为空，代表尚未生成分析。
    latest_report: AnalysisReportArchiveItemResponse | None = None


class WatchlistResponse(BaseModel):
    items: list[WatchlistItemResponse]


class WatchlistFeedItemResponse(BaseModel):
    ts_code: str
    instrument: StockInstrumentResponse | None
    latest_report: AnalysisReportArchiveItemResponse | None
    last_hourly_sync_at: datetime | None
    last_daily_analysis_at: datetime | None


class WatchlistFeedResponse(BaseModel):
    items: list[WatchlistFeedItemResponse]
