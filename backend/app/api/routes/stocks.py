import asyncio
import json
from datetime import date, datetime, timedelta
from decimal import Decimal
from math import isnan
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.auth import get_current_user
from app.cache.redis import get_redis_client
from app.core.settings import get_settings
from app.db.session import get_db_session
from app.integrations.tushare_gateway import TushareGateway
from app.models.stock_adj_factor import StockAdjFactor
from app.models.stock_daily_snapshot import StockDailySnapshot
from app.models.stock_instrument import StockInstrument
from app.models.stock_kline_bar import StockKlineBar
from app.models.stock_trade_calendar import StockTradeCalendar
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
from app.services.stock_sync_service import (
    STOCK_BASIC_FULL_STATUSES,
    sync_stock_basic_full,
)


router = APIRouter()
_daily_cache_lock_guard = asyncio.Lock()
_daily_cache_singleflight_locks: dict[str, asyncio.Lock] = {}
TUSHARE_DAILY_CACHE_PREFIX = "stocks:daily:tushare"
TUSHARE_TRADE_CAL_CACHE_PREFIX = "stocks:trade_cal:tushare"
TUSHARE_ADJ_FACTOR_CACHE_PREFIX = "stocks:adj_factor:tushare"
SUPPORTED_KLINE_PERIODS: tuple[str, ...] = ("daily", "weekly", "monthly")


def _parse_list_status_filter(value: str) -> list[str]:
    normalized_value = value.strip().upper()
    if not normalized_value:
        return ["L"]
    if normalized_value == "ALL":
        return list(STOCK_BASIC_FULL_STATUSES)

    parsed: list[str] = []
    seen: set[str] = set()
    for raw_status in normalized_value.split(","):
        status_value = raw_status.strip()[:1]
        if status_value not in STOCK_BASIC_FULL_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="invalid list_status, expected ALL or comma-separated values in L,D,P,G",
            )
        if status_value in seen:
            continue
        seen.add(status_value)
        parsed.append(status_value)

    return parsed or ["L"]


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


def _parse_yyyymmdd(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y%m%d").date()  # noqa: DTZ007
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="invalid date format, expected YYYYMMDD",
        ) from exc


def _to_optional_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, float) and isnan(value):
        return None

    normalized_value = str(value).strip()
    if not normalized_value:
        return None
    try:
        return float(normalized_value)
    except ValueError:
        return None


def _to_optional_date(value: object) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, float) and isnan(value):
        return None

    normalized_value = str(value).strip()
    if not normalized_value:
        return None

    for format_value in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(normalized_value, format_value).date()  # noqa: DTZ007
        except ValueError:
            continue

    return None


async def _load_daily_rows_from_db(
    *, session: AsyncSession, ts_code: str, limit: int
) -> list[StockDailySnapshotResponse]:
    statement = (
        select(StockDailySnapshot)
        .where(StockDailySnapshot.ts_code == ts_code)
        .order_by(StockDailySnapshot.trade_date.desc())
        .limit(limit)
    )
    snapshots = (await session.execute(statement)).scalars().all()
    return [_to_daily_snapshot_response(snapshot) for snapshot in snapshots]


def _is_quote_complete(value: StockDailySnapshotResponse | None) -> bool:
    if value is None:
        return False
    return value.close is not None and value.trade_date is not None


async def _load_latest_snapshots_map(
    *,
    session: AsyncSession,
    ts_codes: list[str],
) -> dict[str, StockDailySnapshotResponse]:
    if not ts_codes:
        return {}

    # 关键流程：先读 stock_daily_snapshots 作为“首选快照源”，优先复用已有同步结果，
    # 避免首页列表每次都回源到第三方行情接口。
    statement = (
        select(StockDailySnapshot)
        .where(StockDailySnapshot.ts_code.in_(ts_codes))
        .order_by(StockDailySnapshot.ts_code, StockDailySnapshot.trade_date.desc())
    )
    snapshots = (await session.execute(statement)).scalars().all()
    result: dict[str, StockDailySnapshotResponse] = {}
    for snapshot in snapshots:
        if snapshot.ts_code in result:
            continue
        result[snapshot.ts_code] = _to_daily_snapshot_response(snapshot)
    return result


async def _load_latest_daily_kline_map(
    *,
    session: AsyncSession,
    ts_codes: list[str],
) -> dict[str, StockDailySnapshotResponse]:
    if not ts_codes:
        return {}

    # 关键流程：当 snapshots 不完整时，再回退读取 daily 周期 kline 持久化表。
    # 这里按 trade_date 倒序取每个 ts_code 的第一条，确保拿到最近可用交易日。
    statement = (
        select(StockKlineBar)
        .where(StockKlineBar.ts_code.in_(ts_codes))
        .where(StockKlineBar.period == "daily")
        .order_by(StockKlineBar.ts_code, StockKlineBar.trade_date.desc())
    )
    bars = (await session.execute(statement)).scalars().all()
    result: dict[str, StockDailySnapshotResponse] = {}
    for bar in bars:
        if bar.ts_code in result:
            continue
        result[bar.ts_code] = _to_kline_snapshot_response(bar)
    return result


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
        mapped = _map_tushare_daily_row_to_snapshot_response(
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
            await _upsert_kline_rows(
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


def _parse_period(value: str) -> str:
    normalized_value = value.strip().lower()
    if normalized_value in SUPPORTED_KLINE_PERIODS:
        return normalized_value
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail="invalid period, expected daily, weekly, or monthly",
    )


def _to_optional_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, float) and isnan(value):
        return None

    normalized_value = str(value).strip()
    if not normalized_value:
        return None
    try:
        return Decimal(normalized_value)
    except Exception:
        return None


def _parse_is_open(value: str | None) -> str | None:
    if value is None:
        return None
    normalized_value = value.strip()
    if not normalized_value:
        return None
    if normalized_value in {"0", "1"}:
        return normalized_value
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail="invalid is_open, expected 0 or 1",
    )


def _resolve_calendar_date_range(
    *,
    start_date: str | None,
    end_date: str | None,
) -> tuple[str, str]:
    resolved_end = _parse_yyyymmdd(end_date) if end_date else date.today()
    resolved_start = (
        _parse_yyyymmdd(start_date)
        if start_date
        else resolved_end - timedelta(days=400)
    )
    if resolved_start > resolved_end:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="start_date must be earlier than or equal to end_date",
        )

    return resolved_start.strftime("%Y%m%d"), resolved_end.strftime("%Y%m%d")


def _to_trade_cal_cache_key(
    *,
    exchange: str,
    start_date: str,
    end_date: str,
    is_open: str | None,
) -> str:
    cache_is_open = is_open or "ALL"
    return f"{TUSHARE_TRADE_CAL_CACHE_PREFIX}:{exchange}:{start_date}:{end_date}:{cache_is_open}"


def _to_adj_factor_cache_key(
    *,
    ts_code: str,
    start_date: str,
    end_date: str,
    limit: int,
    trade_date: str | None,
) -> str:
    cache_trade_date = trade_date or "ALL"
    return (
        f"{TUSHARE_ADJ_FACTOR_CACHE_PREFIX}:"
        f"{ts_code}:{start_date}:{end_date}:{limit}:{cache_trade_date}"
    )


def _to_trade_calendar_response(
    calendar: StockTradeCalendar,
) -> StockTradeCalendarResponse:
    return StockTradeCalendarResponse(
        exchange=calendar.exchange,
        cal_date=calendar.cal_date,
        is_open=calendar.is_open,
        pretrade_date=calendar.pretrade_date,
    )


def _to_adj_factor_response(adj_factor: StockAdjFactor) -> StockAdjFactorResponse:
    return StockAdjFactorResponse(
        ts_code=adj_factor.ts_code,
        trade_date=adj_factor.trade_date,
        adj_factor=float(adj_factor.adj_factor),
    )


def _to_kline_snapshot_response(row: StockKlineBar) -> StockDailySnapshotResponse:
    return StockDailySnapshotResponse(
        ts_code=row.ts_code,
        trade_date=row.trade_date,
        open=_to_float(row.open),
        high=_to_float(row.high),
        low=_to_float(row.low),
        close=_to_float(row.close),
        pre_close=_to_float(row.pre_close),
        change=_to_float(row.change),
        pct_chg=_to_float(row.pct_chg),
        vol=_to_float(row.vol),
        amount=_to_float(row.amount),
        turnover_rate=None,
        volume_ratio=None,
        pe=None,
        pb=None,
        total_mv=None,
        circ_mv=None,
    )


async def _load_kline_rows_from_db(
    *,
    session: AsyncSession,
    ts_code: str,
    period: str,
    start_date: str,
    end_date: str,
    limit: int,
) -> list[StockDailySnapshotResponse]:
    statement = (
        select(StockKlineBar)
        .where(StockKlineBar.ts_code == ts_code)
        .where(StockKlineBar.period == period)
        .where(StockKlineBar.trade_date >= _parse_yyyymmdd(start_date))
        .where(StockKlineBar.trade_date <= _parse_yyyymmdd(end_date))
        .order_by(StockKlineBar.trade_date.desc())
        .limit(limit)
    )
    rows = (await session.execute(statement)).scalars().all()
    return [_to_kline_snapshot_response(item) for item in rows]


async def _upsert_kline_rows(
    *,
    session: AsyncSession,
    ts_code: str,
    period: str,
    rows: list[dict[str, Any]],
) -> None:
    for raw_row in rows:
        trade_date = _to_optional_date(raw_row.get("trade_date"))
        if trade_date is None:
            continue

        bar = await session.get(StockKlineBar, (ts_code, period, trade_date))
        if bar is None:
            bar = StockKlineBar(ts_code=ts_code, period=period, trade_date=trade_date)
            session.add(bar)

        bar.end_date = _to_optional_date(raw_row.get("end_date"))
        bar.open = _to_optional_decimal(raw_row.get("open"))
        bar.high = _to_optional_decimal(raw_row.get("high"))
        bar.low = _to_optional_decimal(raw_row.get("low"))
        bar.close = _to_optional_decimal(raw_row.get("close"))
        bar.pre_close = _to_optional_decimal(raw_row.get("pre_close"))
        bar.change = _to_optional_decimal(raw_row.get("change"))
        bar.pct_chg = _to_optional_decimal(raw_row.get("pct_chg"))
        bar.vol = _to_optional_decimal(raw_row.get("vol"))
        bar.amount = _to_optional_decimal(raw_row.get("amount"))


async def _load_trade_cal_rows_from_db(
    *,
    session: AsyncSession,
    exchange: str,
    start_date: str,
    end_date: str,
    is_open: str | None,
) -> list[StockTradeCalendarResponse]:
    statement = (
        select(StockTradeCalendar)
        .where(StockTradeCalendar.exchange == exchange)
        .where(StockTradeCalendar.cal_date >= _parse_yyyymmdd(start_date))
        .where(StockTradeCalendar.cal_date <= _parse_yyyymmdd(end_date))
    )
    if is_open is not None:
        statement = statement.where(StockTradeCalendar.is_open == is_open)

    statement = statement.order_by(StockTradeCalendar.cal_date.desc())
    rows = (await session.execute(statement)).scalars().all()
    return [_to_trade_calendar_response(item) for item in rows]


async def _upsert_trade_cal_rows(
    *,
    session: AsyncSession,
    exchange: str,
    rows: list[dict[str, Any]],
) -> None:
    for raw_row in rows:
        cal_date = _to_optional_date(raw_row.get("cal_date"))
        if cal_date is None:
            continue

        calendar = await session.get(StockTradeCalendar, (exchange, cal_date))
        if calendar is None:
            calendar = StockTradeCalendar(
                exchange=exchange, cal_date=cal_date, is_open="0"
            )
            session.add(calendar)

        calendar.is_open = str(raw_row.get("is_open") or "0").strip()[:1] or "0"
        calendar.pretrade_date = _to_optional_date(raw_row.get("pretrade_date"))


async def _load_adj_factor_rows_from_db(
    *,
    session: AsyncSession,
    ts_code: str,
    start_date: str,
    end_date: str,
    trade_date: str | None,
    limit: int,
) -> list[StockAdjFactorResponse]:
    statement = (
        select(StockAdjFactor)
        .where(StockAdjFactor.ts_code == ts_code)
        .where(StockAdjFactor.trade_date >= _parse_yyyymmdd(start_date))
        .where(StockAdjFactor.trade_date <= _parse_yyyymmdd(end_date))
    )
    if trade_date:
        statement = statement.where(
            StockAdjFactor.trade_date == _parse_yyyymmdd(trade_date)
        )

    statement = statement.order_by(StockAdjFactor.trade_date.desc()).limit(limit)
    rows = (await session.execute(statement)).scalars().all()
    return [_to_adj_factor_response(item) for item in rows]


async def _upsert_adj_factor_rows(
    *,
    session: AsyncSession,
    ts_code: str,
    rows: list[dict[str, Any]],
) -> None:
    for raw_row in rows:
        trade_date = _to_optional_date(raw_row.get("trade_date"))
        adj_factor = _to_optional_decimal(raw_row.get("adj_factor"))
        if trade_date is None or adj_factor is None:
            continue

        row = await session.get(StockAdjFactor, (ts_code, trade_date))
        if row is None:
            row = StockAdjFactor(
                ts_code=ts_code, trade_date=trade_date, adj_factor=adj_factor
            )
            session.add(row)
            continue

        row.adj_factor = adj_factor


async def _read_cached_daily_rows(
    cache_key: str,
) -> list[StockDailySnapshotResponse] | None:
    try:
        raw_payload = await get_redis_client().get(cache_key)
    except Exception:
        return None

    if raw_payload is None:
        return None

    try:
        payload = json.loads(raw_payload)
    except json.JSONDecodeError:
        try:
            await get_redis_client().delete(cache_key)
        except Exception:
            pass
        return None

    return [StockDailySnapshotResponse.model_validate(item) for item in payload]


async def _write_cached_daily_rows(
    cache_key: str,
    rows: list[StockDailySnapshotResponse],
    ttl_seconds: int,
) -> None:
    cache_payload = [item.model_dump(mode="json") for item in rows]
    try:
        await get_redis_client().set(
            cache_key,
            json.dumps(cache_payload, ensure_ascii=False),
            ex=ttl_seconds,
        )
    except Exception:
        return


async def _get_singleflight_lock(cache_key: str) -> asyncio.Lock:
    async with _daily_cache_lock_guard:
        existing_lock = _daily_cache_singleflight_locks.get(cache_key)
        if existing_lock is None:
            existing_lock = asyncio.Lock()
            _daily_cache_singleflight_locks[cache_key] = existing_lock
        return existing_lock


def _resolve_tushare_kline_date_range(
    *,
    limit: int,
    trade_date: str | None,
    start_date: str | None,
    end_date: str | None,
) -> tuple[str, str]:
    if trade_date:
        trade_day = _parse_yyyymmdd(trade_date)
        resolved = trade_day.strftime("%Y%m%d")
        return resolved, resolved

    resolved_end = _parse_yyyymmdd(end_date) if end_date else date.today()
    resolved_start = (
        _parse_yyyymmdd(start_date)
        if start_date
        else resolved_end - timedelta(days=limit * 3)
    )

    if resolved_start > resolved_end:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="start_date must be earlier than or equal to end_date",
        )

    return resolved_start.strftime("%Y%m%d"), resolved_end.strftime("%Y%m%d")


def _to_tushare_daily_cache_key(
    *,
    ts_code: str,
    period: str,
    start_date: str,
    end_date: str,
    limit: int,
) -> str:
    return (
        f"{TUSHARE_DAILY_CACHE_PREFIX}:"
        f"{ts_code}:{period}:{start_date}:{end_date}:{limit}"
    )


def _map_tushare_daily_row_to_snapshot_response(
    *,
    ts_code: str,
    row: dict[str, object],
) -> StockDailySnapshotResponse | None:
    trade_date = _to_optional_date(row.get("trade_date"))
    if trade_date is None:
        return None

    return StockDailySnapshotResponse(
        ts_code=ts_code,
        trade_date=trade_date,
        open=_to_optional_float(row.get("open")),
        high=_to_optional_float(row.get("high")),
        low=_to_optional_float(row.get("low")),
        close=_to_optional_float(row.get("close")),
        pre_close=_to_optional_float(row.get("pre_close")),
        change=_to_optional_float(row.get("change")),
        pct_chg=_to_optional_float(row.get("pct_chg")),
        vol=_to_optional_float(row.get("vol")),
        amount=_to_optional_float(row.get("amount")),
        turnover_rate=None,
        volume_ratio=None,
        pe=None,
        pb=None,
        total_mv=None,
        circ_mv=None,
    )


@router.get("/stocks", response_model=list[StockListItemResponse])
async def list_stocks(
    keyword: str | None = Query(default=None),
    list_status: str = Query(default="L"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session),
) -> list[StockListItemResponse]:
    list_statuses = _parse_list_status_filter(list_status)
    statement = select(StockInstrument).where(
        StockInstrument.list_status.in_(list_statuses)
    )
    normalized_keyword = keyword.strip() if keyword else ""
    if normalized_keyword:
        wildcard = f"%{normalized_keyword}%"
        statement = statement.where(
            or_(
                StockInstrument.ts_code.ilike(wildcard),
                StockInstrument.symbol.ilike(wildcard),
                StockInstrument.name.ilike(wildcard),
            )
        )

    statement = (
        statement.order_by(StockInstrument.ts_code)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    instruments = (await session.execute(statement)).scalars().all()

    ts_codes = [instrument.ts_code for instrument in instruments]
    quote_by_ts_code = await _load_latest_snapshots_map(
        session=session, ts_codes=ts_codes
    )

    # 关键流程：第一阶段只补 snapshots 缺失项，避免重复覆盖已有快照数据。
    missing_after_snapshot = [
        ts_code
        for ts_code in ts_codes
        if not _is_quote_complete(quote_by_ts_code.get(ts_code))
    ]
    if missing_after_snapshot:
        kline_quote_by_ts_code = await _load_latest_daily_kline_map(
            session=session,
            ts_codes=missing_after_snapshot,
        )
        for ts_code, quote in kline_quote_by_ts_code.items():
            if _is_quote_complete(quote):
                quote_by_ts_code[ts_code] = quote

    # 关键流程：第二阶段只对仍缺失的股票回源 Tushare，控制第三方调用范围。
    missing_after_kline = [
        ts_code
        for ts_code in ts_codes
        if not _is_quote_complete(quote_by_ts_code.get(ts_code))
    ]
    if missing_after_kline:
        tushare_quote_by_ts_code = await _fetch_latest_daily_quotes_from_tushare(
            session=session,
            ts_codes=missing_after_kline,
        )
        for ts_code, quote in tushare_quote_by_ts_code.items():
            if _is_quote_complete(quote):
                quote_by_ts_code[ts_code] = quote

    # 关键流程：列表查询始终补齐“最新交易日快照”，前端无需再发额外请求拼接卡片数据。
    result: list[StockListItemResponse] = []
    for instrument in instruments:
        latest_snapshot = quote_by_ts_code.get(instrument.ts_code)
        result.append(
            StockListItemResponse(
                ts_code=instrument.ts_code,
                symbol=instrument.symbol,
                name=instrument.name,
                fullname=instrument.fullname,
                exchange=instrument.exchange,
                close=(latest_snapshot.close if latest_snapshot is not None else None),
                pct_chg=(
                    latest_snapshot.pct_chg if latest_snapshot is not None else None
                ),
                trade_date=(
                    latest_snapshot.trade_date if latest_snapshot is not None else None
                ),
            )
        )

    return result


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
    normalized_is_open = _parse_is_open(is_open)
    resolved_start_date, resolved_end_date = _resolve_calendar_date_range(
        start_date=start_date,
        end_date=end_date,
    )
    cache_key = _to_trade_cal_cache_key(
        exchange=normalized_exchange,
        start_date=resolved_start_date,
        end_date=resolved_end_date,
        is_open=normalized_is_open,
    )

    try:
        raw_payload = await get_redis_client().get(cache_key)
    except Exception:
        raw_payload = None
    if raw_payload is not None:
        try:
            payload = json.loads(raw_payload)
            return [StockTradeCalendarResponse.model_validate(item) for item in payload]
        except Exception:
            pass

    db_rows = await _load_trade_cal_rows_from_db(
        session=session,
        exchange=normalized_exchange,
        start_date=resolved_start_date,
        end_date=resolved_end_date,
        is_open=normalized_is_open,
    )
    if db_rows:
        try:
            await get_redis_client().set(
                cache_key,
                json.dumps(
                    [item.model_dump(mode="json") for item in db_rows],
                    ensure_ascii=False,
                ),
                ex=get_settings().stock_trade_cal_cache_ttl_seconds,
            )
        except Exception:
            pass
        return db_rows

    singleflight_lock = await _get_singleflight_lock(cache_key)
    async with singleflight_lock:
        settings = get_settings()
        try:
            gateway = TushareGateway(settings.tushare_token)
            tushare_rows = await gateway.fetch_trade_cal_by_range(
                exchange=normalized_exchange,
                start_date=resolved_start_date,
                end_date=resolved_end_date,
                is_open=normalized_is_open,
            )
            # 关键流程：交易日历属于低频基础数据，回源成功后直接持久化，后续优先走数据库。
            await _upsert_trade_cal_rows(
                session=session,
                exchange=normalized_exchange,
                rows=tushare_rows,
            )
            await session.commit()

            result_rows = await _load_trade_cal_rows_from_db(
                session=session,
                exchange=normalized_exchange,
                start_date=resolved_start_date,
                end_date=resolved_end_date,
                is_open=normalized_is_open,
            )
            try:
                await get_redis_client().set(
                    cache_key,
                    json.dumps(
                        [item.model_dump(mode="json") for item in result_rows],
                        ensure_ascii=False,
                    ),
                    ex=settings.stock_trade_cal_cache_ttl_seconds,
                )
            except Exception:
                pass
            return result_rows
        except Exception:
            return db_rows


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

    normalized_period = _parse_period(period)
    resolved_start_date, resolved_end_date = _resolve_tushare_kline_date_range(
        limit=limit,
        trade_date=trade_date,
        start_date=start_date,
        end_date=end_date,
    )
    cache_key = _to_tushare_daily_cache_key(
        ts_code=normalized_ts_code,
        period=normalized_period,
        start_date=resolved_start_date,
        end_date=resolved_end_date,
        limit=limit,
    )
    cached_rows = await _read_cached_daily_rows(cache_key)
    if cached_rows is not None:
        return cached_rows

    db_rows = await _load_kline_rows_from_db(
        session=session,
        ts_code=normalized_ts_code,
        period=normalized_period,
        start_date=resolved_start_date,
        end_date=resolved_end_date,
        limit=limit,
    )
    # 关键流程：先查数据库历史，命中即返回，避免每次页面切换都访问三方接口。
    has_enough_db_rows = len(db_rows) > 0 if trade_date else len(db_rows) >= limit
    if has_enough_db_rows:
        await _write_cached_daily_rows(
            cache_key,
            db_rows,
            get_settings().stock_daily_cache_ttl_seconds,
        )
        return db_rows

    singleflight_lock = await _get_singleflight_lock(cache_key)
    async with singleflight_lock:
        cached_rows_after_lock = await _read_cached_daily_rows(cache_key)
        if cached_rows_after_lock is not None:
            return cached_rows_after_lock

        settings = get_settings()
        try:
            gateway = TushareGateway(settings.tushare_token)
        except ValueError:
            if db_rows:
                return db_rows
            return await _load_daily_rows_from_db(
                session=session,
                ts_code=normalized_ts_code,
                limit=limit,
            )

        try:
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
            await _upsert_kline_rows(
                session=session,
                ts_code=normalized_ts_code,
                period=normalized_period,
                rows=tushare_rows,
            )
            await session.commit()

            mapped_rows: list[StockDailySnapshotResponse] = []
            for row in tushare_rows:
                mapped_row = _map_tushare_daily_row_to_snapshot_response(
                    ts_code=normalized_ts_code,
                    row=row,
                )
                if mapped_row is None:
                    continue
                mapped_rows.append(mapped_row)

            mapped_rows.sort(key=lambda item: item.trade_date, reverse=True)
            result_rows = mapped_rows[:limit]
            await _write_cached_daily_rows(
                cache_key,
                result_rows,
                settings.stock_daily_cache_ttl_seconds,
            )
            return result_rows
        except Exception:
            # 降级分支：第三方行情接口异常时，回退本地历史快照，保证详情页可用性。
            if db_rows:
                return db_rows
            if normalized_period != "daily":
                return []
            return await _load_daily_rows_from_db(
                session=session,
                ts_code=normalized_ts_code,
                limit=limit,
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

    resolved_start_date, resolved_end_date = _resolve_tushare_kline_date_range(
        limit=limit,
        trade_date=trade_date,
        start_date=start_date,
        end_date=end_date,
    )
    cache_key = _to_adj_factor_cache_key(
        ts_code=normalized_ts_code,
        start_date=resolved_start_date,
        end_date=resolved_end_date,
        limit=limit,
        trade_date=trade_date,
    )

    try:
        raw_payload = await get_redis_client().get(cache_key)
    except Exception:
        raw_payload = None
    if raw_payload is not None:
        try:
            payload = json.loads(raw_payload)
            return [StockAdjFactorResponse.model_validate(item) for item in payload]
        except Exception:
            pass

    db_rows = await _load_adj_factor_rows_from_db(
        session=session,
        ts_code=normalized_ts_code,
        start_date=resolved_start_date,
        end_date=resolved_end_date,
        trade_date=trade_date,
        limit=limit,
    )
    has_enough_db_rows = len(db_rows) > 0 if trade_date else len(db_rows) >= limit
    if has_enough_db_rows:
        try:
            await get_redis_client().set(
                cache_key,
                json.dumps(
                    [item.model_dump(mode="json") for item in db_rows],
                    ensure_ascii=False,
                ),
                ex=get_settings().stock_adj_factor_cache_ttl_seconds,
            )
        except Exception:
            pass
        return db_rows

    singleflight_lock = await _get_singleflight_lock(cache_key)
    async with singleflight_lock:
        settings = get_settings()
        try:
            gateway = TushareGateway(settings.tushare_token)
            tushare_rows = await gateway.fetch_adj_factor_by_range(
                ts_code=normalized_ts_code,
                start_date=resolved_start_date,
                end_date=resolved_end_date,
            )
            # 关键流程：复权因子是可复用的长期数据，回源后立即落库，后续优先 DB 命中。
            await _upsert_adj_factor_rows(
                session=session,
                ts_code=normalized_ts_code,
                rows=tushare_rows,
            )
            await session.commit()

            result_rows = await _load_adj_factor_rows_from_db(
                session=session,
                ts_code=normalized_ts_code,
                start_date=resolved_start_date,
                end_date=resolved_end_date,
                trade_date=trade_date,
                limit=limit,
            )
            try:
                await get_redis_client().set(
                    cache_key,
                    json.dumps(
                        [item.model_dump(mode="json") for item in result_rows],
                        ensure_ascii=False,
                    ),
                    ex=settings.stock_adj_factor_cache_ttl_seconds,
                )
            except Exception:
                pass
            return result_rows
        except Exception:
            return db_rows
