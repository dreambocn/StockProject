from datetime import datetime

from pydantic import BaseModel


class HotNewsItemResponse(BaseModel):
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


class MacroImpactCandidateResponse(BaseModel):
    ts_code: str
    symbol: str
    name: str
    industry: str | None


class MacroImpactProfileResponse(BaseModel):
    topic: str
    affected_assets: list[str]
    beneficiary_sectors: list[str]
    pressure_sectors: list[str]
    a_share_targets: list[str]
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
