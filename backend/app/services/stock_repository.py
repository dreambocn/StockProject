from datetime import date, datetime
from decimal import Decimal
from math import isnan
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.stock_adj_factor import StockAdjFactor
from app.models.stock_daily_snapshot import StockDailySnapshot
from app.models.stock_kline_bar import StockKlineBar
from app.models.stock_trade_calendar import StockTradeCalendar
from app.schemas.stocks import (
    StockAdjFactorResponse,
    StockDailySnapshotResponse,
    StockTradeCalendarResponse,
)


def _to_float(value: object) -> float | None:
    if value is None:
        return None
    return float(value)


def _parse_yyyymmdd(value: str) -> date:
    return datetime.strptime(value, "%Y%m%d").date()  # noqa: DTZ007


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


async def load_daily_rows_from_db(
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


async def load_latest_snapshots_map(
    *,
    session: AsyncSession,
    ts_codes: list[str],
) -> dict[str, StockDailySnapshotResponse]:
    if not ts_codes:
        return {}

    # 关键流程：列表查询优先读取 snapshots 作为首选快照源，
    # 复用已有同步结果，减少回源外部行情接口。
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


async def load_latest_daily_kline_map(
    *,
    session: AsyncSession,
    ts_codes: list[str],
) -> dict[str, StockDailySnapshotResponse]:
    if not ts_codes:
        return {}

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


async def load_kline_rows_from_db(
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


async def upsert_kline_rows(
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


async def load_trade_cal_rows_from_db(
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


async def upsert_trade_cal_rows(
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


async def load_adj_factor_rows_from_db(
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


async def upsert_adj_factor_rows(
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
