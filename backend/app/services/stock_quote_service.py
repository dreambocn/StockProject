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


def _slice_price_windows(
    rows: list[StockDailySnapshot | StockKlineBar],
    *,
    anchor_dates: list[date],
    window_size: int,
) -> dict[date, list[dict[str, object]]]:
    windows: dict[date, list[dict[str, object]]] = {}
    sorted_rows = sorted(rows, key=lambda row: row.trade_date)
    for anchor_date in anchor_dates:
        window_rows = [
            row
            for row in sorted_rows
            if row.trade_date >= anchor_date
        ][:window_size]
        windows[anchor_date] = _to_window_rows_from_snapshots(window_rows)
    return windows


def _all_windows_complete(
    windows: dict[date, list[dict[str, object]]],
    *,
    anchor_dates: list[date],
    window_size: int,
) -> bool:
    return all(len(windows.get(anchor_date, [])) >= window_size for anchor_date in anchor_dates)


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

    windows = await load_price_windows_with_completion(
        session,
        ts_code=ts_code,
        anchor_dates=[anchor_from],
        window_size=window_size,
        fetch_daily_by_range_fn=fetch_daily_by_range_fn,
    )
    return windows.get(anchor_from, [])


async def load_price_windows_with_completion(
    session: AsyncSession,
    *,
    ts_code: str,
    anchor_dates: list[date],
    window_size: int = 5,
    fetch_daily_by_range_fn: DailyRangeFetcher | None = None,
) -> dict[date, list[dict[str, object]]]:
    resolved_anchor_dates = sorted({item for item in anchor_dates if item is not None})
    if not resolved_anchor_dates:
        return {}

    normalized_ts_code = ts_code.strip().upper()
    range_start = min(resolved_anchor_dates)
    range_end = max(resolved_anchor_dates) + timedelta(days=30)

    snapshot_statement = (
        select(StockDailySnapshot)
        .where(StockDailySnapshot.ts_code == normalized_ts_code)
        .where(StockDailySnapshot.trade_date >= range_start)
        .where(StockDailySnapshot.trade_date <= range_end)
        .order_by(StockDailySnapshot.trade_date.asc())
    )
    snapshot_rows = (await session.execute(snapshot_statement)).scalars().all()
    snapshot_windows = _slice_price_windows(
        snapshot_rows,
        anchor_dates=resolved_anchor_dates,
        window_size=window_size,
    )
    if _all_windows_complete(
        snapshot_windows,
        anchor_dates=resolved_anchor_dates,
        window_size=window_size,
    ):
        return snapshot_windows

    kline_statement = (
        select(StockKlineBar)
        .where(StockKlineBar.ts_code == normalized_ts_code)
        .where(StockKlineBar.period == "daily")
        .where(StockKlineBar.trade_date >= range_start)
        .where(StockKlineBar.trade_date <= range_end)
        .order_by(StockKlineBar.trade_date.asc())
    )
    kline_rows = (await session.execute(kline_statement)).scalars().all()
    kline_windows = _slice_price_windows(
        kline_rows,
        anchor_dates=resolved_anchor_dates,
        window_size=window_size,
    )
    if _all_windows_complete(
        kline_windows,
        anchor_dates=resolved_anchor_dates,
        window_size=window_size,
    ):
        return kline_windows

    fetcher = fetch_daily_by_range_fn
    if fetcher is None:
        settings = get_settings()
        try:
            gateway = TushareGateway(settings.tushare_token)
        except ValueError:
            gateway = None

        if gateway is None:
            return kline_windows if kline_rows else snapshot_windows

        async def _default_fetcher(*, ts_code: str, start_date: str, end_date: str):
            return await gateway.fetch_daily_by_range(
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date,
            )

        fetcher = _default_fetcher

    start_date = range_start.strftime("%Y%m%d")
    end_date = range_end.strftime("%Y%m%d")
    try:
        remote_rows = await fetcher(
            ts_code=normalized_ts_code,
            start_date=start_date,
            end_date=end_date,
        )
    except Exception:
        return kline_windows if kline_rows else snapshot_windows
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
            return _slice_price_windows(
                kline_rows,
                anchor_dates=resolved_anchor_dates,
                window_size=window_size,
            )

    return kline_windows if kline_rows else snapshot_windows
