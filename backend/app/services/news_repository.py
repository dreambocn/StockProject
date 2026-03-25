from collections import defaultdict
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.news_event import NewsEvent
from app.models.news_fetch_batch import NewsFetchBatch
from app.models.stock_candidate_evidence_cache import StockCandidateEvidenceCache
from app.schemas.news import (
    CandidateEvidenceItemResponse,
    HotNewsItemResponse,
    NewsEventResponse,
    StockRelatedNewsItemResponse,
)
from app.services.news_fetch_batch_service import load_latest_news_fetch_batch
from app.services.news_latest_query_service import build_latest_news_events_statement
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


def _sortable_datetime(value: datetime | None) -> datetime:
    normalized = _normalize_datetime(value)
    if normalized is not None:
        return normalized
    return datetime.min.replace(tzinfo=UTC)


def build_news_event_logical_key(row: NewsEvent) -> str:
    cluster_key = (row.cluster_key or "").strip()
    if cluster_key:
        return cluster_key

    # 回退键用于缺失 cluster_key 的去重，避免同一事件重复展示。
    published_at = _sortable_datetime(row.published_at).isoformat()
    return "|".join(
        [
            row.scope.strip(),
            (row.ts_code or "").strip(),
            row.title.strip(),
            published_at,
            (row.url or "").strip(),
        ]
    )


def dedupe_news_events_to_latest(rows: list[NewsEvent]) -> list[NewsEvent]:
    # 先按时间/权重降序选最新，再按展示排序回传。
    latest_rows: dict[str, NewsEvent] = {}
    ordered_rows = sorted(
        rows,
        key=lambda row: (
            _sortable_datetime(row.fetched_at),
            _sortable_datetime(row.created_at),
            row.source_priority,
            _sortable_datetime(row.published_at),
        ),
        reverse=True,
    )
    for row in ordered_rows:
        logical_key = build_news_event_logical_key(row)
        if logical_key in latest_rows:
            continue
        latest_rows[logical_key] = row

    deduped_rows = list(latest_rows.values())
    deduped_rows.sort(
        key=lambda row: (
            _sortable_datetime(row.published_at),
            _sortable_datetime(row.fetched_at),
            _sortable_datetime(row.created_at),
        ),
        reverse=True,
    )
    return deduped_rows


def _to_news_event_response(row: NewsEvent) -> NewsEventResponse:
    return NewsEventResponse(
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


def _build_news_scope_statement(
    *,
    scope: str,
    cache_variant: str,
    ts_code: str | None = None,
):
    statement = (
        select(NewsEvent)
        .where(NewsEvent.scope == scope)
        .where(NewsEvent.cache_variant == cache_variant)
    )
    if ts_code is not None:
        statement = statement.where(NewsEvent.ts_code == ts_code)
    return statement


async def _load_latest_news_batch_or_fetched_at(
    *,
    session: AsyncSession,
    scope: str,
    cache_variant: str,
    ts_code: str | None = None,
) -> tuple[NewsFetchBatch | None, datetime | None]:
    # 优先使用批次表时间，缺失时回退到新闻表最新 fetched_at。
    latest_batch = await load_latest_news_fetch_batch(
        session,
        scope=scope,
        cache_variant=cache_variant,
        ts_code=ts_code,
    )
    if latest_batch is not None:
        return latest_batch, _normalize_datetime(latest_batch.fetched_at)

    fallback_statement = select(func.max(NewsEvent.fetched_at)).where(
        NewsEvent.scope == scope,
        NewsEvent.cache_variant == cache_variant,
    )
    if ts_code is not None:
        fallback_statement = fallback_statement.where(NewsEvent.ts_code == ts_code)
    fallback_fetched_at = (await session.execute(fallback_statement)).scalar_one_or_none()
    return None, fallback_fetched_at


async def replace_hot_news_rows(
    *,
    session: AsyncSession,
    cache_variant: str,
    fetched_at: datetime,
    batch_id: str | None = None,
    rows: list[HotNewsItemResponse],
) -> None:
    # 关键归档边界：热点新闻改为按抓取批次追加保存，数据库保留历史批次，
    # 页面和分析默认只读取最新视图，不再通过覆盖写入抹掉历史。
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
                batch_id=batch_id,
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
    latest_batch, latest_fetched_at = await _load_latest_news_batch_or_fetched_at(
        session=session,
        scope="hot",
        cache_variant=cache_variant,
    )
    if latest_fetched_at is None:
        return []

    statement = _build_news_scope_statement(
        scope="hot",
        cache_variant=cache_variant,
    )
    if latest_batch is not None:
        statement = statement.where(NewsEvent.batch_id == latest_batch.id)
    else:
        # 兼容旧数据：未写入批次时按最新 fetched_at 回退。
        statement = statement.where(NewsEvent.fetched_at == latest_fetched_at)
    statement = statement.order_by(
        NewsEvent.source_priority.desc(),
        NewsEvent.published_at.desc(),
        NewsEvent.created_at.desc(),
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
    _latest_batch, latest_fetched_at = await _load_latest_news_batch_or_fetched_at(
        session=session,
        scope="hot",
        cache_variant=cache_variant,
    )
    return latest_fetched_at


async def replace_policy_news_rows(
    *,
    session: AsyncSession,
    fetched_at: datetime,
    batch_id: str | None = None,
    rows: list[NewsEventResponse],
) -> None:
    # 关键归档边界：政策事件保留历史批次，默认读取最新抓取批次，
    # 便于页面展示与大模型分析共享一份可回放的归档数据。
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
                batch_id=batch_id,
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
    latest_batch, latest_fetched_at = await _load_latest_news_batch_or_fetched_at(
        session=session,
        scope="policy",
        cache_variant="policy_source",
    )
    if latest_fetched_at is None:
        return []

    statement = _build_news_scope_statement(
        scope="policy",
        cache_variant="policy_source",
    )
    if latest_batch is not None:
        statement = statement.where(NewsEvent.batch_id == latest_batch.id)
    else:
        statement = statement.where(NewsEvent.fetched_at == latest_fetched_at)
    statement = statement.order_by(NewsEvent.published_at.desc(), NewsEvent.created_at.desc()).limit(limit)
    rows = (await session.execute(statement)).scalars().all()
    return [_to_news_event_response(row) for row in rows]


async def load_latest_policy_news_fetch_at(
    *,
    session: AsyncSession,
) -> datetime | None:
    _latest_batch, latest_fetched_at = await _load_latest_news_batch_or_fetched_at(
        session=session,
        scope="policy",
        cache_variant="policy_source",
    )
    return latest_fetched_at


async def replace_stock_news_rows(
    *,
    session: AsyncSession,
    ts_code: str,
    symbol: str,
    cache_variant: str,
    fetched_at: datetime,
    batch_id: str | None = None,
    rows: list[StockRelatedNewsItemResponse],
) -> None:
    # 关键归档边界：个股新闻/公告按股票和抓取批次追加保存，
    # 既保留历史版本，又让详情页继续只消费最新一批数据。
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
                batch_id=batch_id,
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
    latest_batch, latest_fetched_at = await _load_latest_news_batch_or_fetched_at(
        session=session,
        scope="stock",
        ts_code=ts_code,
        cache_variant=cache_variant,
    )
    if latest_fetched_at is None:
        return []

    statement = _build_news_scope_statement(
        scope="stock",
        cache_variant=cache_variant,
        ts_code=ts_code,
    )
    if latest_batch is not None:
        statement = statement.where(NewsEvent.batch_id == latest_batch.id)
    else:
        statement = statement.where(NewsEvent.fetched_at == latest_fetched_at)
    statement = statement.order_by(NewsEvent.published_at.desc(), NewsEvent.created_at.desc()).limit(limit)
    rows = (await session.execute(statement)).scalars().all()
    return [_to_stock_news_response(row) for row in rows]


async def load_latest_stock_news_fetch_at(
    *,
    session: AsyncSession,
    ts_code: str,
    cache_variant: str,
) -> datetime | None:
    _latest_batch, latest_fetched_at = await _load_latest_news_batch_or_fetched_at(
        session=session,
        scope="stock",
        ts_code=ts_code,
        cache_variant=cache_variant,
    )
    return latest_fetched_at


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
    batch_mode: str = "latest",
) -> list[NewsEventResponse]:
    base_statement = select(NewsEvent)
    if scope:
        base_statement = base_statement.where(NewsEvent.scope == scope)
    if ts_code:
        base_statement = base_statement.where(NewsEvent.ts_code == ts_code)
    if topic:
        base_statement = base_statement.where(NewsEvent.macro_topic == topic)
    if published_from is not None:
        base_statement = base_statement.where(NewsEvent.published_at >= published_from)
    if published_to is not None:
        base_statement = base_statement.where(NewsEvent.published_at <= published_to)

    if batch_mode == "all":
        statement = (
            base_statement.order_by(
                NewsEvent.published_at.desc(),
                NewsEvent.fetched_at.desc(),
                NewsEvent.created_at.desc(),
            )
            .offset(offset)
            .limit(limit)
        )
        rows = (await session.execute(statement)).scalars().all()
        return [_to_news_event_response(row) for row in rows]

    latest_statement = build_latest_news_events_statement(
        base_statement=base_statement,
        apply_default_order=True,
    )
    latest_statement = latest_statement.offset(offset).limit(limit)
    rows = (await session.execute(latest_statement)).scalars().all()
    return [_to_news_event_response(row) for row in rows]


async def replace_stock_candidate_evidence_rows(
    *,
    session: AsyncSession,
    evidence_kind: str,
    fetched_at: datetime,
    rows: list[CandidateEvidenceItemResponse],
) -> None:
    # 关键归档边界：候选证据改为按抓取批次追加保存，方便后续大模型按时间回放；
    # Redis 承担最新批次的热缓存，数据库保留历史批次作为冷数据真相源。
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
    latest_fetched_at = await load_latest_candidate_evidence_fetch_at(
        session=session,
        evidence_kind=evidence_kind,
    )
    if latest_fetched_at is None:
        return []

    statement = (
        select(StockCandidateEvidenceCache)
        .where(StockCandidateEvidenceCache.evidence_kind == evidence_kind)
        .where(StockCandidateEvidenceCache.fetched_at == latest_fetched_at)
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
