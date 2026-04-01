from collections import defaultdict
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache.redis import get_redis_client
from app.core.settings import get_settings
from app.integrations.akshare_gateway import (
    fetch_stock_hot_search,
    fetch_stock_research_reports,
)
from app.models.stock_instrument import StockInstrument
from app.schemas.news import (
    CandidateEvidenceItemResponse,
    CandidateEvidenceSourceBreakdownResponse,
    CandidateEvidenceSummaryResponse,
)
from app.services.news_cache_service import get_news_rows
from app.services.news_repository import (
    load_latest_candidate_evidence_fetch_at,
    load_stock_candidate_evidence_rows_from_db,
    replace_stock_candidate_evidence_rows,
)
from app.services.stock_cache_service import (
    RedisClientGetter,
    get_singleflight_lock,
    read_cached_model_rows,
    write_cached_model_rows,
)


FetchCandidateEvidenceRowsFn = Callable[[], Awaitable[list[dict[str, object]]]]

HOT_SEARCH_EVIDENCE_KIND = "hot_search"
RESEARCH_REPORT_EVIDENCE_KIND = "research_report"
HOT_SEARCH_CACHE_KEY = "candidate-evidence:hot-search"
RESEARCH_REPORT_CACHE_KEY = "candidate-evidence:research-report"


def _normalize_ts_code_list(ts_codes: list[str]) -> list[str]:
    # 统一股票代码并去重，避免对同一标的重复拉取与缓存写入。
    normalized: list[str] = []
    seen: set[str] = set()
    for item in ts_codes:
        normalized_code = item.strip().upper()
        if not normalized_code or normalized_code in seen:
            continue
        normalized.append(normalized_code)
        seen.add(normalized_code)
    return normalized


def _normalize_symbol(value: object | None) -> str | None:
    if value is None:
        return None
    raw = str(value).strip().upper()
    if not raw:
        return None
    if "." in raw:
        raw = raw.split(".", maxsplit=1)[0]
    digits = "".join(ch for ch in raw if ch.isdigit())
    return digits or raw


def _parse_datetime(value: object | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    text = str(value).strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00").replace("/", "-")
    for fmt in (
        None,
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%Y%m%d",
    ):
        try:
            # 多格式容错解析，避免三方字段格式变化导致整批数据丢失。
            parsed = (
                datetime.fromisoformat(normalized)
                if fmt is None
                else datetime.strptime(normalized, fmt)
            )
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=UTC)
            return parsed.astimezone(UTC)
        except ValueError:
            continue
    return None


def _build_hot_search_summary(raw_row: dict[str, object]) -> str:
    summary_parts: list[str] = []
    rank = raw_row.get("当前排名") or raw_row.get("排名") or raw_row.get("rank")
    if rank not in (None, ""):
        summary_parts.append(f"百度热搜排名第 {rank} 位")
    search_index = (
        raw_row.get("搜索指数")
        or raw_row.get("热度")
        or raw_row.get("search_index")
    )
    if search_index not in (None, ""):
        summary_parts.append(f"搜索热度 {search_index}")
    return "；".join(summary_parts) or "进入百度热搜榜"


def _build_research_report_summary(raw_row: dict[str, object]) -> str:
    summary_parts: list[str] = []
    institution = raw_row.get("机构") or raw_row.get("评级机构") or raw_row.get("institution")
    rating = raw_row.get("东财评级") or raw_row.get("评级") or raw_row.get("rating")
    if institution:
        summary_parts.append(f"{institution}发布研报")
    if rating:
        summary_parts.append(f"评级 {rating}")
    return "；".join(summary_parts) or "近 30 日新增研报关注"


def _resolve_instrument(
    raw_row: dict[str, object],
    *,
    instruments_by_symbol: dict[str, StockInstrument],
    instruments_by_name: dict[str, StockInstrument],
) -> StockInstrument | None:
    # 先按代码匹配，再按名称匹配，避免名称重名时误配。
    symbol = _normalize_symbol(
        raw_row.get("股票代码")
        or raw_row.get("代码")
        or raw_row.get("symbol")
        or raw_row.get("ts_code")
    )
    if symbol and symbol in instruments_by_symbol:
        return instruments_by_symbol[symbol]

    name = str(
        raw_row.get("股票名称")
        or raw_row.get("股票简称")
        or raw_row.get("名称")
        or raw_row.get("name")
        or ""
    ).strip()
    if name and name in instruments_by_name:
        return instruments_by_name[name]
    return None


def _map_hot_search_rows(
    *,
    raw_rows: list[dict[str, object]],
    fetched_at: datetime,
    instruments_by_symbol: dict[str, StockInstrument],
    instruments_by_name: dict[str, StockInstrument],
) -> list[CandidateEvidenceItemResponse]:
    mapped: list[CandidateEvidenceItemResponse] = []
    for raw_row in raw_rows:
        instrument = _resolve_instrument(
            raw_row,
            instruments_by_symbol=instruments_by_symbol,
            instruments_by_name=instruments_by_name,
        )
        if instrument is None:
            continue

        mapped.append(
            CandidateEvidenceItemResponse(
                ts_code=instrument.ts_code,
                symbol=instrument.symbol,
                name=instrument.name,
                evidence_kind=HOT_SEARCH_EVIDENCE_KIND,
                title=f"{instrument.name}进入百度热搜",
                summary=_build_hot_search_summary(raw_row),
                published_at=(
                    _parse_datetime(
                        raw_row.get("更新时间")
                        or raw_row.get("更新时间")
                        or raw_row.get("时间")
                        or raw_row.get("date")
                    )
                    or fetched_at
                ),
                url=str(raw_row.get("链接") or raw_row.get("url") or "").strip() or None,
                source="baidu_hot_search",
            )
        )
    return mapped


def _map_research_report_rows(
    *,
    raw_rows: list[dict[str, object]],
    instruments_by_symbol: dict[str, StockInstrument],
    instruments_by_name: dict[str, StockInstrument],
) -> list[CandidateEvidenceItemResponse]:
    mapped: list[CandidateEvidenceItemResponse] = []
    for raw_row in raw_rows:
        instrument = _resolve_instrument(
            raw_row,
            instruments_by_symbol=instruments_by_symbol,
            instruments_by_name=instruments_by_name,
        )
        if instrument is None:
            continue

        title = str(
            raw_row.get("报告标题")
            or raw_row.get("标题")
            or raw_row.get("title")
            or f"{instrument.name}研报更新"
        ).strip()
        mapped.append(
            CandidateEvidenceItemResponse(
                ts_code=instrument.ts_code,
                symbol=instrument.symbol,
                name=instrument.name,
                evidence_kind=RESEARCH_REPORT_EVIDENCE_KIND,
                title=title,
                summary=_build_research_report_summary(raw_row),
                published_at=_parse_datetime(
                    raw_row.get("报告日期")
                    or raw_row.get("日期")
                    or raw_row.get("publish_time")
                    or raw_row.get("date")
                ),
                url=str(raw_row.get("链接") or raw_row.get("url") or "").strip() or None,
                source="eastmoney_research_report",
            )
        )
    return mapped


def _filter_recent_research_report_rows(
    rows: list[CandidateEvidenceItemResponse],
    *,
    now: datetime,
) -> list[CandidateEvidenceItemResponse]:
    reference_now = _parse_datetime(now) or datetime.now(UTC)
    window_start = reference_now - timedelta(days=30)
    filtered: list[CandidateEvidenceItemResponse] = []
    for row in rows:
        published_at = _parse_datetime(row.published_at)
        # 无发布时间或超出近30日窗口的研报，不参与候选增强统计与展示
        if published_at is None:
            continue
        if published_at < window_start or published_at > reference_now:
            continue
        filtered.append(row.model_copy(update={"published_at": published_at}))
    return filtered


async def _load_instrument_lookup(
    session: AsyncSession,
) -> tuple[dict[str, StockInstrument], dict[str, StockInstrument]]:
    statement = select(StockInstrument).where(StockInstrument.list_status == "L")
    rows = (await session.execute(statement)).scalars().all()
    instruments_by_symbol = {
        _normalize_symbol(item.symbol) or item.symbol: item for item in rows if item.symbol
    }
    instruments_by_name = {item.name: item for item in rows if item.name}
    return instruments_by_symbol, instruments_by_name


async def _get_evidence_rows(
    *,
    session: AsyncSession,
    evidence_kind: str,
    cache_key: str,
    cache_ttl_seconds: int,
    refresh_window_seconds: int,
    now: datetime,
    fetch_remote_rows: FetchCandidateEvidenceRowsFn,
    mapper: Callable[
        [list[dict[str, object]], datetime, dict[str, StockInstrument], dict[str, StockInstrument]],
        list[CandidateEvidenceItemResponse],
    ]
    | Callable[[list[dict[str, object]], dict[str, StockInstrument], dict[str, StockInstrument]], list[CandidateEvidenceItemResponse]],
    redis_client_getter: RedisClientGetter,
    allow_remote_fetch: bool = True,
    target_ts_codes: list[str] | None = None,
) -> list[CandidateEvidenceItemResponse]:
    async def read_cache(key: str) -> list[CandidateEvidenceItemResponse] | None:
        return await read_cached_model_rows(
            key,
            CandidateEvidenceItemResponse,
            delete_on_decode_error=True,
            redis_client_getter=redis_client_getter,
        )

    async def write_cache(
        key: str,
        rows: list[CandidateEvidenceItemResponse],
        ttl_seconds: int,
    ) -> None:
        await write_cached_model_rows(
            key,
            rows,
            ttl_seconds=ttl_seconds,
            redis_client_getter=redis_client_getter,
        )

    async def load_from_db() -> list[CandidateEvidenceItemResponse]:
        return await load_stock_candidate_evidence_rows_from_db(
            session=session,
            evidence_kind=evidence_kind,
        )

    async def get_last_fetch_at() -> datetime | None:
        return await load_latest_candidate_evidence_fetch_at(
            session=session,
            evidence_kind=evidence_kind,
        )

    async def fetch_remote_and_persist() -> list[CandidateEvidenceItemResponse]:
        if not allow_remote_fetch:
            raise RuntimeError("candidate evidence remote fetch disabled")
        raw_rows = await fetch_remote_rows()
        fetched_at = now
        instruments_by_symbol, instruments_by_name = await _load_instrument_lookup(session)

        if evidence_kind == HOT_SEARCH_EVIDENCE_KIND:
            mapped_rows = _map_hot_search_rows(
                raw_rows=raw_rows,
                fetched_at=fetched_at,
                instruments_by_symbol=instruments_by_symbol,
                instruments_by_name=instruments_by_name,
            )
        else:
            mapped_rows = _map_research_report_rows(
                raw_rows=raw_rows,
                instruments_by_symbol=instruments_by_symbol,
                instruments_by_name=instruments_by_name,
            )

        await replace_stock_candidate_evidence_rows(
            session=session,
            evidence_kind=evidence_kind,
            fetched_at=fetched_at,
            rows=mapped_rows,
        )
        await session.commit()
        return await load_from_db()

    if not allow_remote_fetch:
        cached_rows = await read_cache(cache_key)
        if cached_rows is not None:
            return cached_rows

        # 影响面板默认是“只读最新快照”路径：缓存失效时只查目标股票的数据库行，
        # 不再经过通用新闻缓存流程，避免重复全表读取以及把局部结果误写回全局缓存键。
        return await load_stock_candidate_evidence_rows_from_db(
            session=session,
            evidence_kind=evidence_kind,
            ts_codes=target_ts_codes,
        )

    return await get_news_rows(
        cache_key=cache_key,
        cache_ttl_seconds=cache_ttl_seconds,
        refresh_window_seconds=refresh_window_seconds,
        now=now,
        read_cache=read_cache,
        write_cache=write_cache,
        load_from_db=load_from_db,
        get_last_fetch_at=get_last_fetch_at,
        fetch_remote_and_persist=fetch_remote_and_persist,
        get_singleflight_lock=get_singleflight_lock,
    )


async def _refresh_evidence_rows(
    *,
    session: AsyncSession,
    evidence_kind: str,
    cache_key: str,
    ttl_seconds: int,
    now: datetime,
    fetch_remote_rows: FetchCandidateEvidenceRowsFn,
    redis_client_getter: RedisClientGetter,
) -> list[CandidateEvidenceItemResponse]:
    raw_rows = await fetch_remote_rows()
    instruments_by_symbol, instruments_by_name = await _load_instrument_lookup(session)

    if evidence_kind == HOT_SEARCH_EVIDENCE_KIND:
        mapped_rows = _map_hot_search_rows(
            raw_rows=raw_rows,
            fetched_at=now,
            instruments_by_symbol=instruments_by_symbol,
            instruments_by_name=instruments_by_name,
        )
    else:
        mapped_rows = _map_research_report_rows(
            raw_rows=raw_rows,
            instruments_by_symbol=instruments_by_symbol,
            instruments_by_name=instruments_by_name,
        )

    await replace_stock_candidate_evidence_rows(
        session=session,
        evidence_kind=evidence_kind,
        fetched_at=now,
        rows=mapped_rows,
    )
    await session.commit()
    await write_cached_model_rows(
        cache_key,
        mapped_rows,
        ttl_seconds=ttl_seconds,
        redis_client_getter=redis_client_getter,
    )
    return mapped_rows


def _build_source_breakdown(
    hot_search_count: int,
    research_report_count: int,
) -> list[CandidateEvidenceSourceBreakdownResponse]:
    breakdown: list[CandidateEvidenceSourceBreakdownResponse] = []
    if hot_search_count > 0:
        breakdown.append(
            CandidateEvidenceSourceBreakdownResponse(
                source=HOT_SEARCH_EVIDENCE_KIND,
                count=hot_search_count,
            )
        )
    if research_report_count > 0:
        breakdown.append(
            CandidateEvidenceSourceBreakdownResponse(
                source=RESEARCH_REPORT_EVIDENCE_KIND,
                count=research_report_count,
            )
        )
    return breakdown


async def get_candidate_evidence_snapshots(
    *,
    session: AsyncSession,
    ts_codes: list[str],
    now: datetime | None = None,
    evidence_item_limit: int = 3,
    fetch_hot_search_rows: FetchCandidateEvidenceRowsFn = fetch_stock_hot_search,
    fetch_research_report_rows: FetchCandidateEvidenceRowsFn = fetch_stock_research_reports,
    redis_client_getter: RedisClientGetter | None = None,
    hot_search_cache_ttl_seconds: int | None = None,
    hot_search_refresh_window_seconds: int | None = None,
    research_report_cache_ttl_seconds: int | None = None,
    research_report_refresh_window_seconds: int | None = None,
    allow_remote_fetch: bool = True,
) -> dict[str, CandidateEvidenceSummaryResponse]:
    normalized_ts_codes = _normalize_ts_code_list(ts_codes)
    if not normalized_ts_codes:
        return {}

    settings = get_settings()
    resolved_now = now or datetime.now(UTC)
    # 关键缓存边界：默认值必须返回真实 Redis 客户端，不能用 None 占位，
    # 否则缓存读写会退化成 AttributeError，热点页每次都会重复走慢路径。
    resolved_redis_getter = redis_client_getter or get_redis_client

    hot_search_rows: list[CandidateEvidenceItemResponse] = []
    research_report_rows: list[CandidateEvidenceItemResponse] = []

    try:
        hot_search_rows = await _get_evidence_rows(
            session=session,
            evidence_kind=HOT_SEARCH_EVIDENCE_KIND,
            cache_key=HOT_SEARCH_CACHE_KEY,
            cache_ttl_seconds=hot_search_cache_ttl_seconds
            or settings.candidate_hot_search_cache_ttl_seconds,
            refresh_window_seconds=hot_search_refresh_window_seconds
            or settings.candidate_hot_search_cache_ttl_seconds,
            now=resolved_now,
            fetch_remote_rows=fetch_hot_search_rows,
            mapper=_map_hot_search_rows,
            redis_client_getter=resolved_redis_getter,
            allow_remote_fetch=allow_remote_fetch,
            target_ts_codes=normalized_ts_codes,
        )
    except Exception:
        # 热搜抓取失败不影响研报与页面整体渲染，直接降级为空列表。
        hot_search_rows = []

    try:
        research_report_rows = await _get_evidence_rows(
            session=session,
            evidence_kind=RESEARCH_REPORT_EVIDENCE_KIND,
            cache_key=RESEARCH_REPORT_CACHE_KEY,
            cache_ttl_seconds=research_report_cache_ttl_seconds
            or settings.candidate_research_report_cache_ttl_seconds,
            refresh_window_seconds=research_report_refresh_window_seconds
            or settings.candidate_research_report_cache_ttl_seconds,
            now=resolved_now,
            fetch_remote_rows=fetch_research_report_rows,
            mapper=_map_research_report_rows,
            redis_client_getter=resolved_redis_getter,
            allow_remote_fetch=allow_remote_fetch,
            target_ts_codes=normalized_ts_codes,
        )
    except Exception:
        # 研报抓取失败同样降级为无数据，避免阻塞其余证据展示。
        research_report_rows = []

    research_report_rows = _filter_recent_research_report_rows(
        research_report_rows,
        now=resolved_now,
    )

    target_set = set(normalized_ts_codes)
    grouped_rows: dict[str, list[CandidateEvidenceItemResponse]] = defaultdict(list)
    for row in hot_search_rows + research_report_rows:
        if row.ts_code not in target_set:
            continue
        grouped_rows[row.ts_code].append(row)

    snapshots: dict[str, CandidateEvidenceSummaryResponse] = {}
    for ts_code in normalized_ts_codes:
        rows = grouped_rows.get(ts_code, [])
        hot_search_count = sum(
            1 for item in rows if item.evidence_kind == HOT_SEARCH_EVIDENCE_KIND
        )
        research_report_count = sum(
            1 for item in rows if item.evidence_kind == RESEARCH_REPORT_EVIDENCE_KIND
        )
        ordered_rows = sorted(
            rows,
            key=lambda item: (
                item.published_at or datetime.min.replace(tzinfo=UTC),
                1 if item.evidence_kind == HOT_SEARCH_EVIDENCE_KIND else 0,
            ),
            reverse=True,
        )
        latest_published_at = ordered_rows[0].published_at if ordered_rows else None
        snapshots[ts_code] = CandidateEvidenceSummaryResponse(
            ts_code=ts_code,
            hot_search_count=hot_search_count,
            research_report_count=research_report_count,
            latest_published_at=latest_published_at,
            source_breakdown=_build_source_breakdown(
                hot_search_count,
                research_report_count,
            ),
            evidence_items=ordered_rows[: max(1, min(evidence_item_limit, 5))],
        )

    return snapshots


async def refresh_candidate_evidence_caches(
    *,
    session: AsyncSession,
    now: datetime | None = None,
    redis_client_getter: RedisClientGetter | None = None,
    fetch_hot_search_rows: FetchCandidateEvidenceRowsFn = fetch_stock_hot_search,
    fetch_research_report_rows: FetchCandidateEvidenceRowsFn = fetch_stock_research_reports,
    include_research_report: bool = True,
) -> dict[str, int]:
    settings = get_settings()
    resolved_now = now or datetime.now(UTC)
    # 后台刷新统一写入 Redis，确保前台“只读缓存”的路径稳定。
    resolved_redis_getter = redis_client_getter or get_redis_client

    hot_rows = await _refresh_evidence_rows(
        session=session,
        evidence_kind=HOT_SEARCH_EVIDENCE_KIND,
        cache_key=HOT_SEARCH_CACHE_KEY,
        ttl_seconds=settings.candidate_hot_search_cache_ttl_seconds,
        now=resolved_now,
        fetch_remote_rows=fetch_hot_search_rows,
        redis_client_getter=resolved_redis_getter,
    )

    research_rows: list[CandidateEvidenceItemResponse] = []
    if include_research_report:
        research_rows = await _refresh_evidence_rows(
            session=session,
            evidence_kind=RESEARCH_REPORT_EVIDENCE_KIND,
            cache_key=RESEARCH_REPORT_CACHE_KEY,
            ttl_seconds=settings.candidate_research_report_cache_ttl_seconds,
            now=resolved_now,
            fetch_remote_rows=fetch_research_report_rows,
            redis_client_getter=resolved_redis_getter,
        )

    return {
        "hot_search_rows": len(hot_rows),
        "research_report_rows": len(research_rows),
    }
