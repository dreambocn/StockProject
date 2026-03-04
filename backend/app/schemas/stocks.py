from datetime import date

from pydantic import BaseModel, ConfigDict


class StockListItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ts_code: str
    symbol: str
    name: str
    fullname: str | None
    exchange: str | None
    close: float | None
    pct_chg: float | None
    trade_date: date | None


class StockInstrumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ts_code: str
    symbol: str
    name: str
    area: str | None
    industry: str | None
    fullname: str | None
    enname: str | None
    cnspell: str | None
    market: str | None
    exchange: str | None
    curr_type: str | None
    list_status: str
    list_date: date | None
    delist_date: date | None
    is_hs: str | None
    act_name: str | None
    act_ent_type: str | None


class AdminStockPageResponse(BaseModel):
    items: list[StockInstrumentResponse]
    total: int
    page: int
    page_size: int


class StockDailySnapshotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ts_code: str
    trade_date: date
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    pre_close: float | None
    change: float | None
    pct_chg: float | None
    vol: float | None
    amount: float | None
    turnover_rate: float | None
    volume_ratio: float | None
    pe: float | None
    pb: float | None
    total_mv: float | None
    circ_mv: float | None


class StockDetailResponse(BaseModel):
    instrument: StockInstrumentResponse
    latest_snapshot: StockDailySnapshotResponse | None


class StockBasicSyncResponse(BaseModel):
    message: str
    total: int
    created: int
    updated: int
    list_statuses: list[str]
