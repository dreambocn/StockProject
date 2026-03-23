from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.news_event import NewsEvent
from app.schemas.news import (
    HotNewsItemResponse,
    NewsEventResponse,
    StockRelatedNewsItemResponse,
)


def _to_hot_news_response(row: NewsEvent) -> HotNewsItemResponse:
    return HotNewsItemResponse(
        title=row.title,
        summary=row.summary,
        published_at=row.published_at,
        url=row.url,
        source=row.source,
        macro_topic=row.macro_topic or "other",
    )


def _to_stock_news_response(row: NewsEvent) -> StockRelatedNewsItemResponse:
    return StockRelatedNewsItemResponse(
        ts_code=row.ts_code or "",
        symbol=row.symbol or "",
        title=row.title,
        summary=row.summary,
        published_at=row.published_at,
        url=row.url,
        publisher=row.publisher,
        source=row.source,
    )


async def replace_hot_news_rows(
    *,
    session: AsyncSession,
    cache_variant: str,
    fetched_at: datetime,
    rows: list[HotNewsItemResponse],
) -> None:
    await session.execute(
        delete(NewsEvent)
        .where(NewsEvent.scope == "hot")
        .where(NewsEvent.cache_variant == cache_variant)
    )
    for row in rows:
        session.add(
            NewsEvent(
                scope="hot",
                cache_variant=cache_variant,
                ts_code=None,
                symbol=None,
                title=row.title,
                summary=row.summary,
                published_at=row.published_at,
                url=row.url,
                publisher=None,
                source=row.source,
                macro_topic=row.macro_topic,
                fetched_at=fetched_at,
            )
        )


async def load_hot_news_rows_from_db(
    *,
    session: AsyncSession,
    cache_variant: str,
    topic: str,
    limit: int,
) -> list[HotNewsItemResponse]:
    statement = (
        select(NewsEvent)
        .where(NewsEvent.scope == "hot")
        .where(NewsEvent.cache_variant == cache_variant)
    )
    if topic != "all":
        statement = statement.where(NewsEvent.macro_topic == topic)
    statement = statement.order_by(
        NewsEvent.published_at.desc(), NewsEvent.created_at.desc()
    ).limit(limit)
    rows = (await session.execute(statement)).scalars().all()
    return [_to_hot_news_response(row) for row in rows]


async def load_latest_hot_news_fetch_at(
    *,
    session: AsyncSession,
    cache_variant: str,
) -> datetime | None:
    statement = (
        select(func.max(NewsEvent.fetched_at))
        .where(NewsEvent.scope == "hot")
        .where(NewsEvent.cache_variant == cache_variant)
    )
    return (await session.execute(statement)).scalar_one_or_none()


async def replace_policy_news_rows(
    *,
    session: AsyncSession,
    fetched_at: datetime,
    rows: list[NewsEventResponse],
) -> None:
    await session.execute(
        delete(NewsEvent)
        .where(NewsEvent.scope == "policy")
        .where(NewsEvent.cache_variant == "policy_source")
    )
    for row in rows:
        session.add(
            NewsEvent(
                scope="policy",
                cache_variant="policy_source",
                ts_code=None,
                symbol=None,
                title=row.title,
                summary=row.summary,
                published_at=row.published_at,
                url=row.url,
                publisher=row.publisher,
                source=row.source,
                macro_topic=row.macro_topic,
                fetched_at=fetched_at,
            )
        )


async def load_policy_news_rows(
    *,
    session: AsyncSession,
    limit: int,
) -> list[NewsEventResponse]:
    statement = (
        select(NewsEvent)
        .where(NewsEvent.scope == "policy")
        .where(NewsEvent.cache_variant == "policy_source")
        .order_by(NewsEvent.published_at.desc(), NewsEvent.created_at.desc())
        .limit(limit)
    )
    rows = (await session.execute(statement)).scalars().all()
    return [
        NewsEventResponse(
            scope=row.scope,
            cache_variant=row.cache_variant,
            ts_code=row.ts_code,
            symbol=row.symbol,
            title=row.title,
            summary=row.summary,
            published_at=row.published_at,
            url=row.url,
            publisher=row.publisher,
            source=row.source,
            macro_topic=row.macro_topic,
            fetched_at=row.fetched_at,
        )
        for row in rows
    ]

async def replace_stock_news_rows(
    *,
    session: AsyncSession,
    ts_code: str,
    symbol: str,
    cache_variant: str,
    fetched_at: datetime,
    rows: list[StockRelatedNewsItemResponse],
) -> None:
    await session.execute(
        delete(NewsEvent)
        .where(NewsEvent.scope == "stock")
        .where(NewsEvent.ts_code == ts_code)
        .where(NewsEvent.cache_variant == cache_variant)
    )
    for row in rows:
        session.add(
            NewsEvent(
                scope="stock",
                cache_variant=cache_variant,
                ts_code=ts_code,
                symbol=symbol,
                title=row.title,
                summary=row.summary,
                published_at=row.published_at,
                url=row.url,
                publisher=row.publisher,
                source=row.source,
                macro_topic=None,
                fetched_at=fetched_at,
            )
        )


async def load_stock_news_rows_from_db(
    *,
    session: AsyncSession,
    ts_code: str,
    cache_variant: str,
    limit: int,
) -> list[StockRelatedNewsItemResponse]:
    statement = (
        select(NewsEvent)
        .where(NewsEvent.scope == "stock")
        .where(NewsEvent.ts_code == ts_code)
        .where(NewsEvent.cache_variant == cache_variant)
        .order_by(NewsEvent.published_at.desc(), NewsEvent.created_at.desc())
        .limit(limit)
    )
    rows = (await session.execute(statement)).scalars().all()
    return [_to_stock_news_response(row) for row in rows]


async def load_latest_stock_news_fetch_at(
    *,
    session: AsyncSession,
    ts_code: str,
    cache_variant: str,
) -> datetime | None:
    statement = (
        select(func.max(NewsEvent.fetched_at))
        .where(NewsEvent.scope == "stock")
        .where(NewsEvent.ts_code == ts_code)
        .where(NewsEvent.cache_variant == cache_variant)
    )
    return (await session.execute(statement)).scalar_one_or_none()


async def query_news_events(
    *,
    session: AsyncSession,
    scope: str | None,
    ts_code: str | None,
    topic: str | None,
    published_from: datetime | None,
    published_to: datetime | None,
    limit: int,
    offset: int = 0,
) -> list[NewsEventResponse]:
    statement = select(NewsEvent)
    if scope:
        statement = statement.where(NewsEvent.scope == scope)
    if ts_code:
        statement = statement.where(NewsEvent.ts_code == ts_code)
    if topic:
        statement = statement.where(NewsEvent.macro_topic == topic)
    if published_from is not None:
        statement = statement.where(NewsEvent.published_at >= published_from)
    if published_to is not None:
        statement = statement.where(NewsEvent.published_at <= published_to)

    statement = (
        statement.order_by(NewsEvent.published_at.desc(), NewsEvent.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    rows = (await session.execute(statement)).scalars().all()
    return [
        NewsEventResponse(
            scope=row.scope,
            cache_variant=row.cache_variant,
            ts_code=row.ts_code,
            symbol=row.symbol,
            title=row.title,
            summary=row.summary,
            published_at=row.published_at,
            url=row.url,
            publisher=row.publisher,
            source=row.source,
            macro_topic=row.macro_topic,
            fetched_at=row.fetched_at,
        )
        for row in rows
    ]
