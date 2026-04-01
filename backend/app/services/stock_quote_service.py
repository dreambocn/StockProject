from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import get_settings
from app.integrations.tushare_gateway import TushareGateway
from app.models.stock_daily_snapshot import StockDailySnapshot
from app.models.stock_kline_bar import StockKlineBar
from app.schemas.stocks import StockDailySnapshotResponse
from app.services.stock_repository import (
    load_latest_daily_kline_map,
    load_latest_snapshots_map,
    upsert_kline_rows,
)
from app.services.stock_tushare_mapper import map_tushare_daily_row_to_snapshot_response


LatestQuoteFetcher = Callable[
    [list[str]],
    Awaitable[dict[str, StockDailySnapshotResponse | dict[str, object]]],
]
DailyRangeFetcher = Callable[
    ...,
    Awaitable[list[dict[str, object]]],
]


def _is_quote_complete(snapshot: StockDailySnapshotResponse | None) -> bool:
    return (
        snapshot is not None
        and snapshot.trade_date is not None
        and snapshot.close is not None
    )


def _normalize_quote_row(
    *,
    ts_code: str,
    value: StockDailySnapshotResponse | dict[str, object] | None,
) -> StockDailySnapshotResponse | None:
    if value is None:
        return None
    if isinstance(value, StockDailySnapshotResponse):
        return value
    return map_tushare_daily_row_to_snapshot_response(ts_code=ts_code, row=value)


def _serialize_kline_row(snapshot: StockDailySnapshotResponse) -> dict[str, object]:
    # 统一把远端行情回写成 daily kline，确保详情页、分析页和列表页复用同一份本地数据。
    return {
        "trade_date": snapshot.trade_date.strftime("%Y%m%d"),
        "open": snapshot.open,
        "high": snapshot.high,
        "low": snapshot.low,
        "close": snapshot.close,
        "pre_close": snapshot.pre_close,
        "change": snapshot.change,
        "pct_chg": snapshot.pct_chg,
        "vol": snapshot.vol,
        "amount": snapshot.amount,
    }


def _to_window_rows_from_snapshots(
    rows: list[StockDailySnapshot | StockKlineBar],
) -> list[dict[str, object]]:
    return [
        {
            "trade_date": row.trade_date,
            "close": float(row.close) if row.close is not None else None,
            "vol": float(row.vol) if row.vol is not None else None,
        }
        for row in rows
    ]


async def fetch_latest_daily_quotes_from_tushare(
    session: AsyncSession,
    *,
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
        current = latest_by_code.get(raw_ts_code)
        if current is None or mapped.trade_date > current.trade_date:
            latest_by_code[raw_ts_code] = mapped

    if not latest_by_code:
        return {}

    try:
        for ts_code, snapshot in latest_by_code.items():
            await upsert_kline_rows(
                session=session,
                ts_code=ts_code,
                period="daily",
                rows=[_serialize_kline_row(snapshot)],
            )
        await session.commit()
    except Exception:
        await session.rollback()

    return latest_by_code


async def load_resolved_latest_snapshot(
    session: AsyncSession,
    *,
    ts_code: str,
    fetch_latest_quotes_fn: LatestQuoteFetcher | None = None,
) -> StockDailySnapshotResponse | None:
    normalized_ts_code = ts_code.strip().upper()
    snapshot_map = await load_latest_snapshots_map(
        session=session,
        ts_codes=[normalized_ts_code],
    )
    snapshot = snapshot_map.get(normalized_ts_code)
    if _is_quote_complete(snapshot):
        return snapshot

    kline_map = await load_latest_daily_kline_map(
        session=session,
        ts_codes=[normalized_ts_code],
    )
    kline_snapshot = kline_map.get(normalized_ts_code)
    if _is_quote_complete(kline_snapshot):
        return kline_snapshot

    fetcher = fetch_latest_quotes_fn
    if fetcher is None:
        async def _default_fetcher(ts_codes: list[str]):
            return await fetch_latest_daily_quotes_from_tushare(
                session,
                ts_codes=ts_codes,
            )

        fetcher = _default_fetcher

    fetched_quotes = await fetcher([normalized_ts_code])
    return _normalize_quote_row(
        ts_code=normalized_ts_code,
        value=fetched_quotes.get(normalized_ts_code),
    )


async def load_price_window_with_completion(
    session: AsyncSession,
    *,
    ts_code: str,
    anchor_from: date | None,
    window_size: int = 5,
    fetch_daily_by_range_fn: DailyRangeFetcher | None = None,
) -> list[dict[str, object]]:
    if anchor_from is None:
        return []

    normalized_ts_code = ts_code.strip().upper()

    snapshot_statement = (
        select(StockDailySnapshot)
        .where(StockDailySnapshot.ts_code == normalized_ts_code)
        .where(StockDailySnapshot.trade_date >= anchor_from)
        .order_by(StockDailySnapshot.trade_date.asc())
        .limit(window_size)
    )
    snapshot_rows = (await session.execute(snapshot_statement)).scalars().all()
    if len(snapshot_rows) >= window_size:
        return _to_window_rows_from_snapshots(snapshot_rows)

    kline_statement = (
        select(StockKlineBar)
        .where(StockKlineBar.ts_code == normalized_ts_code)
        .where(StockKlineBar.period == "daily")
        .where(StockKlineBar.trade_date >= anchor_from)
        .order_by(StockKlineBar.trade_date.asc())
        .limit(window_size)
    )
    kline_rows = (await session.execute(kline_statement)).scalars().all()
    if len(kline_rows) >= window_size:
        return _to_window_rows_from_snapshots(kline_rows)

    fetcher = fetch_daily_by_range_fn
    if fetcher is None:
        settings = get_settings()
        try:
            gateway = TushareGateway(settings.tushare_token)
        except ValueError:
            gateway = None

        if gateway is None:
            return _to_window_rows_from_snapshots(kline_rows or snapshot_rows)

        async def _default_fetcher(*, ts_code: str, start_date: str, end_date: str):
            return await gateway.fetch_daily_by_range(
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date,
            )

        fetcher = _default_fetcher

    start_date = anchor_from.strftime("%Y%m%d")
    end_date = (anchor_from + timedelta(days=30)).strftime("%Y%m%d")
    remote_rows = await fetcher(
        ts_code=normalized_ts_code,
        start_date=start_date,
        end_date=end_date,
    )
    if remote_rows:
        await upsert_kline_rows(
            session=session,
            ts_code=normalized_ts_code,
            period="daily",
            rows=remote_rows,
        )
        await session.commit()

        kline_rows = (await session.execute(kline_statement)).scalars().all()
        if kline_rows:
            return _to_window_rows_from_snapshots(kline_rows)

    return _to_window_rows_from_snapshots(kline_rows or snapshot_rows)
