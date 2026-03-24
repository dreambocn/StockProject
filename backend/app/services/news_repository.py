from collections import defaultdict
from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.news_event import NewsEvent
from app.models.stock_candidate_evidence_cache import StockCandidateEvidenceCache
from app.schemas.news import (
    CandidateEvidenceItemResponse,
    HotNewsItemResponse,
    NewsEventResponse,
    StockRelatedNewsItemResponse,
)
from app.services.news_normalization_service import (
    build_cluster_key,
    normalize_provider,
    providers_to_source_coverage,
)


def _to_hot_news_response(row: NewsEvent, providers: list[str]) -> HotNewsItemResponse:
    return HotNewsItemResponse(
        event_id=row.id,
        cluster_key=row.cluster_key or row.id,
        providers=providers,
        source_coverage=providers_to_source_coverage(providers),
        title=row.title,
        summary=row.summary,
        published_at=row.published_at,
        url=row.url,
        source=row.source,
        macro_topic=row.macro_topic or "other",
    )


def _normalize_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _to_stock_news_response(row: NewsEvent) -> StockRelatedNewsItemResponse:
    return StockRelatedNewsItemResponse(
        ts_code=row.ts_code or "",
        symbol=row.symbol or "",
        title=row.title,
        summary=row.summary,
        published_at=_normalize_datetime(row.published_at),
        url=row.url,
        publisher=row.publisher,
        source=row.source,
    )


def _derive_news_provider(source: str) -> str:
    return normalize_provider(None, source)


def _derive_source_priority(provider: str) -> int:
    if provider == "tushare":
        return 30
    if provider == "akshare":
        return 20
    return 10


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
        provider = normalize_provider(
            row.providers[0] if row.providers else None,
            row.source,
        )
        session.add(
            NewsEvent(
                id=row.event_id or None,
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
                provider=provider,
                external_id=None,
                cluster_key=row.cluster_key
                or build_cluster_key(
                    title=row.title,
                    published_at=row.published_at,
                    macro_topic=row.macro_topic,
                ),
                source_priority=_derive_source_priority(provider),
                evidence_kind="hot",
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
        .order_by(
            NewsEvent.source_priority.desc(),
            NewsEvent.published_at.desc(),
            NewsEvent.created_at.desc(),
        )
    )
    if topic != "all":
        statement = statement.where(NewsEvent.macro_topic == topic)

    rows = (await session.execute(statement)).scalars().all()
    grouped_rows: dict[str, list[NewsEvent]] = defaultdict(list)
    for row in rows:
        grouped_rows[row.cluster_key or row.id].append(row)

    aggregated: list[HotNewsItemResponse] = []
    for key, grouped in grouped_rows.items():
        representative = grouped[0]
        providers = sorted(
            {
                normalize_provider(item.provider, item.source)
                for item in grouped
            }
        )
        aggregated.append(_to_hot_news_response(representative, providers))

    aggregated.sort(key=lambda item: item.published_at or datetime.min, reverse=True)
    return aggregated[:limit]


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
        provider = _derive_news_provider(row.source)
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
                provider=provider,
                external_id=None,
                cluster_key=build_cluster_key(
                    title=row.title,
                    published_at=row.published_at,
                    macro_topic=row.macro_topic,
                ),
                source_priority=_derive_source_priority(provider),
                evidence_kind="macro_event",
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
        provider = _derive_news_provider(row.source)
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
                provider=provider,
                external_id=None,
                cluster_key=build_cluster_key(
                    title=row.title,
                    published_at=row.published_at,
                    macro_topic=None,
                ),
                source_priority=_derive_source_priority(provider),
                evidence_kind="announcement" if row.source == "cninfo_announcement" else "stock_news",
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


async def replace_stock_candidate_evidence_rows(
    *,
    session: AsyncSession,
    evidence_kind: str,
    fetched_at: datetime,
    rows: list[CandidateEvidenceItemResponse],
) -> None:
    await session.execute(
        delete(StockCandidateEvidenceCache).where(
            StockCandidateEvidenceCache.evidence_kind == evidence_kind
        )
    )
    for row in rows:
        session.add(
            StockCandidateEvidenceCache(
                evidence_kind=evidence_kind,
                ts_code=row.ts_code,
                symbol=row.symbol,
                name=row.name,
                title=row.title,
                summary=row.summary,
                published_at=row.published_at,
                url=row.url,
                source=row.source,
                fetched_at=fetched_at,
            )
        )


async def load_stock_candidate_evidence_rows_from_db(
    *,
    session: AsyncSession,
    evidence_kind: str,
) -> list[CandidateEvidenceItemResponse]:
    statement = (
        select(StockCandidateEvidenceCache)
        .where(StockCandidateEvidenceCache.evidence_kind == evidence_kind)
        .order_by(
            StockCandidateEvidenceCache.published_at.desc(),
            StockCandidateEvidenceCache.created_at.desc(),
        )
    )
    rows = (await session.execute(statement)).scalars().all()
    return [
        CandidateEvidenceItemResponse(
            ts_code=row.ts_code,
            symbol=row.symbol,
            name=row.name,
            evidence_kind=row.evidence_kind,
            title=row.title,
            summary=row.summary,
            published_at=_normalize_datetime(row.published_at),
            url=row.url,
            source=row.source,
        )
        for row in rows
    ]


async def load_latest_candidate_evidence_fetch_at(
    *,
    session: AsyncSession,
    evidence_kind: str,
) -> datetime | None:
    statement = (
        select(func.max(StockCandidateEvidenceCache.fetched_at))
        .where(StockCandidateEvidenceCache.evidence_kind == evidence_kind)
    )
    return (await session.execute(statement)).scalar_one_or_none()
