from datetime import UTC, date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.auth import get_current_user
from app.cache.redis import get_redis_client
from app.core.settings import get_settings
from app.db.session import get_db_session
from app.integrations.akshare_gateway import (
    fetch_stock_announcements,
    fetch_stock_news,
)
from app.integrations.tushare_gateway import TushareGateway
from app.models.stock_daily_snapshot import StockDailySnapshot
from app.models.stock_instrument import StockInstrument
from app.models.user import User
from app.schemas.stocks import (
    StockAdjFactorResponse,
    StockBasicSyncResponse,
    StockDailySnapshotResponse,
    StockDetailResponse,
    StockInstrumentResponse,
    StockListItemResponse,
    StockTradeCalendarResponse,
)
from app.schemas.news import StockRelatedNewsItemResponse
from app.services.news_cache_service import get_news_rows
from app.services.news_cache_version_service import (
    build_news_cache_version_key,
    format_news_cache_version,
    read_news_cache_version,
    resolve_news_cache_data_key,
    write_news_cache_version,
)
from app.services.news_fetch_batch_service import (
    NEWS_FETCH_STATUS_FAILED,
    NEWS_FETCH_STATUS_PARTIAL,
    NEWS_FETCH_STATUS_SUCCESS,
    create_news_fetch_batch,
    finalize_news_fetch_batch,
)
from app.services.stock_sync_service import (
    STOCK_BASIC_FULL_STATUSES,
    sync_stock_basic_full,
)
from app.services.stock_list_status import parse_stock_list_status_filter
from app.services.stock_listing_service import list_stock_items_with_quote_completion
from app.services.stock_tushare_mapper import (
    map_tushare_daily_row_to_snapshot_response,
)
from app.services.stock_query_policy import (
    parse_is_open as policy_parse_is_open,
    parse_period as policy_parse_period,
    resolve_calendar_date_range as policy_resolve_calendar_date_range,
    resolve_tushare_kline_date_range as policy_resolve_tushare_kline_date_range,
    to_adj_factor_cache_key as policy_to_adj_factor_cache_key,
    to_trade_cal_cache_key as policy_to_trade_cal_cache_key,
    to_tushare_daily_cache_key as policy_to_tushare_daily_cache_key,
)
from app.services.stock_repository import (
    load_adj_factor_rows_from_db as repo_load_adj_factor_rows_from_db,
    load_daily_rows_from_db as repo_load_daily_rows_from_db,
    load_kline_rows_from_db as repo_load_kline_rows_from_db,
    load_latest_daily_kline_map as repo_load_latest_daily_kline_map,
    load_latest_snapshots_map as repo_load_latest_snapshots_map,
    load_trade_cal_rows_from_db as repo_load_trade_cal_rows_from_db,
    upsert_adj_factor_rows as repo_upsert_adj_factor_rows,
    upsert_kline_rows as repo_upsert_kline_rows,
    upsert_trade_cal_rows as repo_upsert_trade_cal_rows,
)
from app.services.stock_daily_service import get_stock_daily_rows
from app.services.stock_cache_service import (
    get_singleflight_lock as cache_get_singleflight_lock,
    read_cached_model_rows,
    write_cached_model_rows,
)
from app.services.stock_reference_data_service import (
    get_adj_factor_rows,
    get_trade_calendar_rows,
)
from app.services.news_mapper_service import (
    map_stock_announcement_rows,
    map_stock_news_rows,
)
from app.services.news_repository import (
    load_latest_stock_news_fetch_at,
    load_stock_news_rows_from_db,
    replace_stock_news_rows,
)


router = APIRouter()
TUSHARE_DAILY_CACHE_PREFIX = "stocks:daily:tushare"
TUSHARE_TRADE_CAL_CACHE_PREFIX = "stocks:trade_cal:tushare"
TUSHARE_ADJ_FACTOR_CACHE_PREFIX = "stocks:adj_factor:tushare"
STOCK_NEWS_CACHE_PREFIX = "stocks:news"
SUPPORTED_KLINE_PERIODS: tuple[str, ...] = ("daily", "weekly", "monthly")


def _normalize_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


async def _read_versioned_stock_news_cache(
    *,
    base_cache_key: str,
    version_key: str,
    model_type: type[BaseModel],
    last_fetch_at: datetime | None,
    delete_on_decode_error: bool = False,
) -> list[BaseModel] | None:
    settings = get_settings()
    legacy_fallback_enabled = bool(
        getattr(settings, "news_cache_version_legacy_fallback_enabled", True)
    )
    legacy_fallback_seconds = int(
        getattr(settings, "news_cache_version_legacy_fallback_seconds", 3600)
    )
    version = await read_news_cache_version(
        version_key=version_key,
        redis_client_getter=get_redis_client,
    )
    if version is not None:
        return await read_cached_model_rows(
            resolve_news_cache_data_key(
                base_cache_key=base_cache_key,
                version=version,
            ),
            model_type,
            delete_on_decode_error=delete_on_decode_error,
            redis_client_getter=get_redis_client,
        )

    if not legacy_fallback_enabled:
        return None

    normalized_last_fetch_at = _normalize_datetime(last_fetch_at)
    if (
        normalized_last_fetch_at is not None
        and datetime.now(UTC) - normalized_last_fetch_at
        > timedelta(seconds=legacy_fallback_seconds)
    ):
        return None

    return await read_cached_model_rows(
        base_cache_key,
        model_type,
        delete_on_decode_error=delete_on_decode_error,
        redis_client_getter=get_redis_client,
    )


async def _write_versioned_stock_news_cache(
    *,
    base_cache_key: str,
    version_key: str,
    rows: list[BaseModel],
    ttl_seconds: int,
) -> None:
    version = await read_news_cache_version(
        version_key=version_key,
        redis_client_getter=get_redis_client,
    )
    await write_cached_model_rows(
        resolve_news_cache_data_key(
            base_cache_key=base_cache_key,
            version=version,
        ),
        rows,
        ttl_seconds=ttl_seconds,
        redis_client_getter=get_redis_client,
    )


async def _fetch_latest_snapshot(
    session: AsyncSession, ts_code: str
) -> StockDailySnapshot | None:
    statement = (
        select(StockDailySnapshot)
        .where(StockDailySnapshot.ts_code == ts_code)
        .order_by(StockDailySnapshot.trade_date.desc())
        .limit(1)
    )
    return (await session.execute(statement)).scalar_one_or_none()


def _to_float(value: object) -> float | None:
    if value is None:
        return None
    return float(value)


def _to_daily_snapshot_response(
    snapshot: StockDailySnapshot,
) -> StockDailySnapshotResponse:
    return StockDailySnapshotResponse(
        ts_code=snapshot.ts_code,
        trade_date=snapshot.trade_date,
        open=_to_float(snapshot.open),
        high=_to_float(snapshot.high),
        low=_to_float(snapshot.low),
        close=_to_float(snapshot.close),
        pre_close=_to_float(snapshot.pre_close),
        change=_to_float(snapshot.change),
        pct_chg=_to_float(snapshot.pct_chg),
        vol=_to_float(snapshot.vol),
        amount=_to_float(snapshot.amount),
        turnover_rate=_to_float(snapshot.turnover_rate),
        volume_ratio=_to_float(snapshot.volume_ratio),
        pe=_to_float(snapshot.pe),
        pb=_to_float(snapshot.pb),
        total_mv=_to_float(snapshot.total_mv),
        circ_mv=_to_float(snapshot.circ_mv),
    )


async def _fetch_latest_daily_quotes_from_tushare(
    *,
    session: AsyncSession,
    ts_codes: list[str],
) -> dict[str, StockDailySnapshotResponse]:
    if not ts_codes:
        return {}

    settings = get_settings()
    try:
        gateway = TushareGateway(settings.tushare_token)
    except ValueError:
        return {}

    end_date = date.today()
    start_date = end_date - timedelta(days=45)
    try:
        rows = await gateway.fetch_daily_by_range(
            ts_code=",".join(ts_codes),
            start_date=start_date.strftime("%Y%m%d"),
            end_date=end_date.strftime("%Y%m%d"),
        )
    except Exception:
        return {}

    # 关键流程：首页列表补全必须以“最近可用交易日”为准，按 ts_code 选取最新 trade_date 的行情。
    latest_by_code: dict[str, StockDailySnapshotResponse] = {}
    for row in rows:
        raw_ts_code = str(row.get("ts_code") or "").strip().upper()
        if not raw_ts_code:
            continue
        mapped = map_tushare_daily_row_to_snapshot_response(
            ts_code=raw_ts_code,
            row=row,
        )
        if mapped is None:
            continue

        existing = latest_by_code.get(raw_ts_code)
        if existing is None or mapped.trade_date > existing.trade_date:
            latest_by_code[raw_ts_code] = mapped

    if not latest_by_code:
        return {}

    # 关键状态流转：回源成功后立即落库，后续列表请求优先命中数据库，避免重复访问三方接口。
    try:
        for ts_code, quote in latest_by_code.items():
            await repo_upsert_kline_rows(
                session=session,
                ts_code=ts_code,
                period="daily",
                rows=[
                    {
                        "trade_date": quote.trade_date.strftime("%Y%m%d"),
                        "open": quote.open,
                        "high": quote.high,
                        "low": quote.low,
                        "close": quote.close,
                        "pre_close": quote.pre_close,
                        "change": quote.change,
                        "pct_chg": quote.pct_chg,
                        "vol": quote.vol,
                        "amount": quote.amount,
                    }
                ],
            )
        await session.commit()
    except Exception:
        await session.rollback()

    return latest_by_code


@router.get("/stocks", response_model=list[StockListItemResponse])
async def list_stocks(
    keyword: str | None = Query(default=None),
    list_status: str = Query(default="L"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session),
) -> list[StockListItemResponse]:
    try:
        list_statuses = parse_stock_list_status_filter(
            list_status,
            all_statuses=STOCK_BASIC_FULL_STATUSES,
            default_statuses=("L",),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    async def load_latest_snapshots(
        ts_codes: list[str],
    ) -> dict[str, StockDailySnapshotResponse]:
        return await repo_load_latest_snapshots_map(session=session, ts_codes=ts_codes)

    async def load_latest_daily_kline(
        ts_codes: list[str],
    ) -> dict[str, StockDailySnapshotResponse]:
        return await repo_load_latest_daily_kline_map(
            session=session,
            ts_codes=ts_codes,
        )

    async def fetch_latest_tushare(
        ts_codes: list[str],
    ) -> dict[str, StockDailySnapshotResponse]:
        return await _fetch_latest_daily_quotes_from_tushare(
            session=session,
            ts_codes=ts_codes,
        )

    return await list_stock_items_with_quote_completion(
        session=session,
        keyword=keyword,
        list_statuses=list_statuses,
        page=page,
        page_size=page_size,
        load_latest_snapshots=load_latest_snapshots,
        load_latest_daily_kline=load_latest_daily_kline,
        fetch_latest_tushare=fetch_latest_tushare,
    )


@router.post("/stocks/sync/full", response_model=StockBasicSyncResponse)
async def trigger_stock_basic_full_sync(
    current_user: Annotated[User, Depends(get_current_user)],
    session: AsyncSession = Depends(get_db_session),
) -> StockBasicSyncResponse:
    # 鉴权边界：该接口会触发外部数据源全量同步，仅允许已登录用户调用。
    _ = current_user

    settings = get_settings()
    try:
        gateway = TushareGateway(settings.tushare_token)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="tushare token not configured",
        ) from exc

    # 关键流程：全量基础库固定拉取 L/D/P/G，保证数据库主数据覆盖完整状态集合。
    sync_result = await sync_stock_basic_full(
        session,
        gateway,
        list_statuses=STOCK_BASIC_FULL_STATUSES,
    )
    return StockBasicSyncResponse(
        message="stock basic sync completed",
        total=int(sync_result["total"]),
        created=int(sync_result["created"]),
        updated=int(sync_result["updated"]),
        list_statuses=list(sync_result["list_statuses"]),
    )


@router.get(
    "/stocks/trade-cal",
    response_model=list[StockTradeCalendarResponse],
)
async def get_trade_calendar(
    exchange: str = Query(default="SSE"),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    is_open: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db_session),
) -> list[StockTradeCalendarResponse]:
    normalized_exchange = exchange.strip().upper() or "SSE"
    try:
        normalized_is_open = policy_parse_is_open(is_open)
        resolved_start_date, resolved_end_date = policy_resolve_calendar_date_range(
            start_date=start_date,
            end_date=end_date,
        )
        cache_key = policy_to_trade_cal_cache_key(
            prefix=TUSHARE_TRADE_CAL_CACHE_PREFIX,
            exchange=normalized_exchange,
            start_date=resolved_start_date,
            end_date=resolved_end_date,
            is_open=normalized_is_open,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    async def read_cache(
        key: str,
    ) -> list[StockTradeCalendarResponse] | None:
        return await read_cached_model_rows(
            key,
            StockTradeCalendarResponse,
            redis_client_getter=get_redis_client,
        )

    async def write_cache(
        key: str,
        rows: list[StockTradeCalendarResponse],
        ttl_seconds: int,
    ) -> None:
        await write_cached_model_rows(
            key,
            rows,
            ttl_seconds=ttl_seconds,
            redis_client_getter=get_redis_client,
        )

    async def load_from_db() -> list[StockTradeCalendarResponse]:
        return await repo_load_trade_cal_rows_from_db(
            session=session,
            exchange=normalized_exchange,
            start_date=resolved_start_date,
            end_date=resolved_end_date,
            is_open=normalized_is_open,
        )

    async def fetch_from_remote_and_persist() -> list[StockTradeCalendarResponse]:
        settings = get_settings()
        gateway = TushareGateway(settings.tushare_token)
        tushare_rows = await gateway.fetch_trade_cal_by_range(
            exchange=normalized_exchange,
            start_date=resolved_start_date,
            end_date=resolved_end_date,
            is_open=normalized_is_open,
        )
        # 关键流程：交易日历属于低频基础数据，回源成功后直接持久化，后续优先走数据库。
        await repo_upsert_trade_cal_rows(
            session=session,
            exchange=normalized_exchange,
            rows=tushare_rows,
        )
        await session.commit()
        return await load_from_db()

    return await get_trade_calendar_rows(
        cache_key=cache_key,
        cache_ttl_seconds=get_settings().stock_trade_cal_cache_ttl_seconds,
        read_cache=read_cache,
        write_cache=write_cache,
        load_from_db=load_from_db,
        fetch_from_remote_and_persist=fetch_from_remote_and_persist,
        get_singleflight_lock=cache_get_singleflight_lock,
    )


@router.get("/stocks/{ts_code}", response_model=StockDetailResponse)
async def get_stock_detail(
    ts_code: str,
    session: AsyncSession = Depends(get_db_session),
) -> StockDetailResponse:
    normalized_ts_code = ts_code.strip().upper()
    instrument = await session.get(StockInstrument, normalized_ts_code)
    if instrument is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="stock not found",
        )

    latest_snapshot = await _fetch_latest_snapshot(session, normalized_ts_code)
    return StockDetailResponse(
        instrument=StockInstrumentResponse.model_validate(instrument),
        latest_snapshot=(
            _to_daily_snapshot_response(latest_snapshot)
            if latest_snapshot is not None
            else None
        ),
    )


@router.get(
    "/stocks/{ts_code}/news",
    response_model=list[StockRelatedNewsItemResponse],
)
async def get_stock_related_news(
    ts_code: str,
    limit: int = Query(default=100, ge=1, le=200),
    include_announcements: bool = Query(default=True),
    session: AsyncSession = Depends(get_db_session),
) -> list[StockRelatedNewsItemResponse]:
    normalized_ts_code = ts_code.strip().upper()
    instrument = await session.get(StockInstrument, normalized_ts_code)
    if instrument is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="stock not found",
        )

    symbol = instrument.symbol.strip() if instrument.symbol else ""
    if not symbol:
        return []
    cache_variant = "with_announcements" if include_announcements else "news_only"
    cache_key = (
        f"{STOCK_NEWS_CACHE_PREFIX}:{normalized_ts_code}:{cache_variant}:{limit}"
    )
    version_key = build_news_cache_version_key(
        scope="stock",
        cache_variant=cache_variant,
        ts_code=normalized_ts_code,
    )

    async def get_last_fetch_at() -> datetime | None:
        return await load_latest_stock_news_fetch_at(
            session=session,
            ts_code=normalized_ts_code,
            cache_variant=cache_variant,
        )

    async def read_cache(key: str) -> list[StockRelatedNewsItemResponse] | None:
        return await _read_versioned_stock_news_cache(
            base_cache_key=key,
            version_key=version_key,
            model_type=StockRelatedNewsItemResponse,
            last_fetch_at=await get_last_fetch_at(),
            delete_on_decode_error=True,
        )

    async def write_cache(
        key: str,
        rows: list[StockRelatedNewsItemResponse],
        ttl_seconds: int,
    ) -> None:
        await _write_versioned_stock_news_cache(
            base_cache_key=key,
            version_key=version_key,
            rows=rows,
            ttl_seconds=ttl_seconds,
        )

    async def load_from_db() -> list[StockRelatedNewsItemResponse]:
        return await load_stock_news_rows_from_db(
            session=session,
            ts_code=normalized_ts_code,
            cache_variant=cache_variant,
            limit=limit,
        )

    async def fetch_remote_and_persist() -> list[StockRelatedNewsItemResponse]:
        fetched_at = datetime.now(UTC)
        batch = await create_news_fetch_batch(
            session,
            scope="stock",
            cache_variant=cache_variant,
            ts_code=normalized_ts_code,
            trigger_source="api.stocks.news",
            fetched_at=fetched_at,
            started_at=fetched_at,
        )
        provider_stats: list[dict[str, object]] = []
        degrade_reasons: list[str] = []
        try:
            # 关键流程：个股详情页只拉取该股票自身新闻，并把结果统一落库，
            # 1 小时内优先走缓存和数据库，避免切换详情/复看页面时重复打资讯源。
            stock_news_rows = await fetch_stock_news(symbol)
            mapped_stock_news = map_stock_news_rows(
                ts_code=normalized_ts_code,
                symbol=symbol,
                rows=stock_news_rows,
            )
            provider_stats.append(
                {
                    "provider": "eastmoney_stock",
                    "status": "success",
                    "error_type": None,
                    "raw_count": len(stock_news_rows),
                    "mapped_count": len(mapped_stock_news),
                    "persisted_count": len(mapped_stock_news),
                }
            )
            mapped_items = mapped_stock_news

            if include_announcements:
                # 关键业务分支：公告作为强相关补充并入新闻流；若公告源失败，降级为仅新闻，不阻断主流程。
                try:
                    announcement_rows = await fetch_stock_announcements(symbol=symbol)
                    mapped_announcements = map_stock_announcement_rows(
                        ts_code=normalized_ts_code,
                        symbol=symbol,
                        rows=announcement_rows,
                    )
                    provider_stats.append(
                        {
                            "provider": "cninfo_announcement",
                            "status": "success",
                            "error_type": None,
                            "raw_count": len(announcement_rows),
                            "mapped_count": len(mapped_announcements),
                            "persisted_count": len(mapped_announcements),
                        }
                    )
                except Exception as exc:
                    announcement_rows = []
                    mapped_announcements = []
                    provider_stats.append(
                        {
                            "provider": "cninfo_announcement",
                            "status": "failed",
                            "error_type": type(exc).__name__,
                            "raw_count": 0,
                            "mapped_count": 0,
                            "persisted_count": 0,
                        }
                    )
                    degrade_reasons.append("stock.announcement_failed")
                mapped_items = [*mapped_stock_news, *mapped_announcements]
            else:
                provider_stats.append(
                    {
                        "provider": "cninfo_announcement",
                        "status": "skipped",
                        "error_type": None,
                        "raw_count": 0,
                        "mapped_count": 0,
                        "persisted_count": 0,
                    }
                )
        except Exception as exc:
            await finalize_news_fetch_batch(
                session,
                batch=batch,
                status=NEWS_FETCH_STATUS_FAILED,
                finished_at=datetime.now(UTC),
                row_count_raw=0,
                row_count_mapped=0,
                row_count_persisted=0,
                provider_stats=[
                    {
                        "provider": "eastmoney_stock",
                        "status": "failed",
                        "error_type": type(exc).__name__,
                        "raw_count": 0,
                        "mapped_count": 0,
                        "persisted_count": 0,
                    }
                ],
                degrade_reasons=["stock.news_failed"],
                error_type=type(exc).__name__,
                error_message="个股新闻上游抓取失败",
            )
            await session.commit()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="stock news upstream unavailable",
            ) from exc

        if not mapped_items:
            await finalize_news_fetch_batch(
                session,
                batch=batch,
                status=NEWS_FETCH_STATUS_FAILED,
                finished_at=datetime.now(UTC),
                row_count_raw=0,
                row_count_mapped=0,
                row_count_persisted=0,
                provider_stats=provider_stats,
                degrade_reasons=degrade_reasons or ["mapping.empty_after_filter"],
                error_type=None,
                error_message="个股新闻映射后为空，回退到最近批次",
            )
            await session.commit()
            return await load_from_db()

        mapped_items.sort(
            key=lambda item: item.published_at or datetime.min, reverse=True
        )
        await replace_stock_news_rows(
            session=session,
            ts_code=normalized_ts_code,
            symbol=symbol,
            cache_variant=cache_variant,
            fetched_at=fetched_at,
            batch_id=batch.id,
            rows=mapped_items,
        )
        await finalize_news_fetch_batch(
            session,
            batch=batch,
            status=(
                NEWS_FETCH_STATUS_PARTIAL if degrade_reasons else NEWS_FETCH_STATUS_SUCCESS
            ),
            finished_at=datetime.now(UTC),
            row_count_raw=sum(int(item["raw_count"]) for item in provider_stats),
            row_count_mapped=len(mapped_items),
            row_count_persisted=len(mapped_items),
            provider_stats=provider_stats,
            degrade_reasons=degrade_reasons,
        )
        await session.commit()
        await write_news_cache_version(
            version_key=version_key,
            version=format_news_cache_version(fetched_at=fetched_at),
            redis_client_getter=get_redis_client,
        )
        return await load_from_db()

    return await get_news_rows(
        cache_key=cache_key,
        cache_ttl_seconds=get_settings().stock_related_news_cache_ttl_seconds,
        refresh_window_seconds=get_settings().stock_related_news_cache_ttl_seconds,
        now=datetime.now(UTC),
        read_cache=read_cache,
        write_cache=write_cache,
        load_from_db=load_from_db,
        get_last_fetch_at=get_last_fetch_at,
        fetch_remote_and_persist=fetch_remote_and_persist,
        get_singleflight_lock=cache_get_singleflight_lock,
    )


@router.get("/stocks/{ts_code}/daily", response_model=list[StockDailySnapshotResponse])
async def get_stock_daily(
    ts_code: str,
    limit: int = Query(default=60, ge=1, le=240),
    period: str = Query(default="daily"),
    trade_date: str | None = Query(default=None),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db_session),
) -> list[StockDailySnapshotResponse]:
    normalized_ts_code = ts_code.strip().upper()
    instrument = await session.get(StockInstrument, normalized_ts_code)
    if instrument is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="stock not found",
        )

    try:
        normalized_period = policy_parse_period(
            period,
            supported_periods=SUPPORTED_KLINE_PERIODS,
        )
        resolved_start_date, resolved_end_date = (
            policy_resolve_tushare_kline_date_range(
                limit=limit,
                trade_date=trade_date,
                start_date=start_date,
                end_date=end_date,
            )
        )
        cache_key = policy_to_tushare_daily_cache_key(
            prefix=TUSHARE_DAILY_CACHE_PREFIX,
            ts_code=normalized_ts_code,
            period=normalized_period,
            start_date=resolved_start_date,
            end_date=resolved_end_date,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    async def load_kline_from_db() -> list[StockDailySnapshotResponse]:
        return await repo_load_kline_rows_from_db(
            session=session,
            ts_code=normalized_ts_code,
            period=normalized_period,
            start_date=resolved_start_date,
            end_date=resolved_end_date,
            limit=limit,
        )

    async def load_daily_snapshot_fallback() -> list[StockDailySnapshotResponse]:
        return await repo_load_daily_rows_from_db(
            session=session,
            ts_code=normalized_ts_code,
            limit=limit,
        )

    async def read_daily_cache(
        key: str,
    ) -> list[StockDailySnapshotResponse] | None:
        return await read_cached_model_rows(
            key,
            StockDailySnapshotResponse,
            delete_on_decode_error=True,
            redis_client_getter=get_redis_client,
        )

    async def write_daily_cache(
        key: str,
        rows: list[StockDailySnapshotResponse],
        ttl_seconds: int,
    ) -> None:
        await write_cached_model_rows(
            key,
            rows,
            ttl_seconds=ttl_seconds,
            redis_client_getter=get_redis_client,
        )

    async def fetch_remote_and_persist() -> list[StockDailySnapshotResponse]:
        settings = get_settings()
        gateway = TushareGateway(settings.tushare_token)

        if normalized_period == "weekly":
            tushare_rows = await gateway.fetch_weekly_by_range(
                ts_code=normalized_ts_code,
                start_date=resolved_start_date,
                end_date=resolved_end_date,
            )
        elif normalized_period == "monthly":
            tushare_rows = await gateway.fetch_monthly_by_range(
                ts_code=normalized_ts_code,
                start_date=resolved_start_date,
                end_date=resolved_end_date,
            )
        else:
            tushare_rows = await gateway.fetch_daily_by_range(
                ts_code=normalized_ts_code,
                start_date=resolved_start_date,
                end_date=resolved_end_date,
            )

        # 关键状态流转：三方回源成功后立即落库，后续同参数请求可直接走数据库。
        await repo_upsert_kline_rows(
            session=session,
            ts_code=normalized_ts_code,
            period=normalized_period,
            rows=tushare_rows,
        )
        await session.commit()

        mapped_rows: list[StockDailySnapshotResponse] = []
        for row in tushare_rows:
            mapped_row = map_tushare_daily_row_to_snapshot_response(
                ts_code=normalized_ts_code,
                row=row,
            )
            if mapped_row is None:
                continue
            mapped_rows.append(mapped_row)

        mapped_rows.sort(key=lambda item: item.trade_date, reverse=True)
        return mapped_rows[:limit]

    return await get_stock_daily_rows(
        cache_key=cache_key,
        cache_ttl_seconds=get_settings().stock_daily_cache_ttl_seconds,
        period=normalized_period,
        limit=limit,
        trade_date=trade_date,
        read_cache=read_daily_cache,
        write_cache=write_daily_cache,
        load_kline_from_db=load_kline_from_db,
        load_daily_snapshot_fallback=load_daily_snapshot_fallback,
        fetch_remote_and_persist=fetch_remote_and_persist,
        get_singleflight_lock=cache_get_singleflight_lock,
    )


@router.get(
    "/stocks/{ts_code}/adj-factor",
    response_model=list[StockAdjFactorResponse],
)
async def get_adj_factor(
    ts_code: str,
    limit: int = Query(default=240, ge=1, le=2000),
    trade_date: str | None = Query(default=None),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db_session),
) -> list[StockAdjFactorResponse]:
    normalized_ts_code = ts_code.strip().upper()
    instrument = await session.get(StockInstrument, normalized_ts_code)
    if instrument is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="stock not found",
        )

    try:
        resolved_start_date, resolved_end_date = (
            policy_resolve_tushare_kline_date_range(
                limit=limit,
                trade_date=trade_date,
                start_date=start_date,
                end_date=end_date,
            )
        )
        cache_key = policy_to_adj_factor_cache_key(
            prefix=TUSHARE_ADJ_FACTOR_CACHE_PREFIX,
            ts_code=normalized_ts_code,
            start_date=resolved_start_date,
            end_date=resolved_end_date,
            limit=limit,
            trade_date=trade_date,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    async def read_cache(
        key: str,
    ) -> list[StockAdjFactorResponse] | None:
        return await read_cached_model_rows(
            key,
            StockAdjFactorResponse,
            redis_client_getter=get_redis_client,
        )

    async def write_cache(
        key: str,
        rows: list[StockAdjFactorResponse],
        ttl_seconds: int,
    ) -> None:
        await write_cached_model_rows(
            key,
            rows,
            ttl_seconds=ttl_seconds,
            redis_client_getter=get_redis_client,
        )

    async def load_from_db() -> list[StockAdjFactorResponse]:
        return await repo_load_adj_factor_rows_from_db(
            session=session,
            ts_code=normalized_ts_code,
            start_date=resolved_start_date,
            end_date=resolved_end_date,
            trade_date=trade_date,
            limit=limit,
        )

    async def fetch_from_remote_and_load() -> list[StockAdjFactorResponse]:
        settings = get_settings()
        gateway = TushareGateway(settings.tushare_token)
        tushare_rows = await gateway.fetch_adj_factor_by_range(
            ts_code=normalized_ts_code,
            start_date=resolved_start_date,
            end_date=resolved_end_date,
        )
        # 关键流程：复权因子是可复用的长期数据，回源后立即落库，后续优先 DB 命中。
        await repo_upsert_adj_factor_rows(
            session=session,
            ts_code=normalized_ts_code,
            rows=tushare_rows,
        )
        await session.commit()
        return await load_from_db()

    return await get_adj_factor_rows(
        cache_key=cache_key,
        cache_ttl_seconds=get_settings().stock_adj_factor_cache_ttl_seconds,
        read_cache=read_cache,
        write_cache=write_cache,
        load_from_db=load_from_db,
        fetch_from_remote_and_load=fetch_from_remote_and_load,
        has_enough_db_rows=(
            lambda rows: len(rows) > 0 if trade_date else len(rows) >= limit
        ),
        get_singleflight_lock=cache_get_singleflight_lock,
    )
