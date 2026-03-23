from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import get_settings
from app.integrations.akshare_gateway import (
    fetch_stock_announcements,
    fetch_stock_news,
)
from app.integrations.tushare_gateway import TushareGateway
from app.models.analysis_report import AnalysisReport
from app.models.stock_daily_snapshot import StockDailySnapshot
from app.models.stock_instrument import StockInstrument
from app.models.stock_trade_calendar import StockTradeCalendar
from app.models.stock_watch_snapshot import StockWatchSnapshot
from app.models.user_watchlist_item import UserWatchlistItem
from app.services.analysis_service import start_analysis_session
from app.services.news_mapper_service import (
    map_stock_announcement_rows,
    map_stock_news_rows,
)
from app.services.news_repository import replace_stock_news_rows


@dataclass(slots=True)
class DailyAnalysisTarget:
    ts_code: str
    use_web_search: bool


async def list_hourly_sync_targets(session: AsyncSession) -> list[str]:
    statement = select(UserWatchlistItem).where(
        UserWatchlistItem.hourly_sync_enabled.is_(True)
    )
    rows = (await session.execute(statement)).scalars().all()
    targets = sorted({row.ts_code.strip().upper() for row in rows if row.ts_code})
    return targets


async def list_daily_analysis_targets(
    session: AsyncSession,
) -> list[DailyAnalysisTarget]:
    statement = select(UserWatchlistItem).where(
        UserWatchlistItem.daily_analysis_enabled.is_(True)
    )
    rows = (await session.execute(statement)).scalars().all()

    aggregated: dict[str, DailyAnalysisTarget] = {}
    for row in rows:
        normalized_ts_code = row.ts_code.strip().upper()
        if not normalized_ts_code:
            continue
        current = aggregated.get(normalized_ts_code)
        if current is None:
            aggregated[normalized_ts_code] = DailyAnalysisTarget(
                ts_code=normalized_ts_code,
                use_web_search=bool(row.web_search_enabled),
            )
            continue
        if row.web_search_enabled:
            current.use_web_search = True

    return sorted(aggregated.values(), key=lambda item: item.ts_code)


async def mark_hourly_sync_completed(
    session: AsyncSession,
    *,
    ts_code: str,
    synced_at: datetime,
) -> None:
    statement = select(UserWatchlistItem).where(UserWatchlistItem.ts_code == ts_code)
    rows = (await session.execute(statement)).scalars().all()
    for row in rows:
        if row.hourly_sync_enabled:
            row.last_hourly_sync_at = synced_at


async def mark_daily_analysis_completed(
    session: AsyncSession,
    *,
    ts_code: str,
    analyzed_at: datetime,
) -> None:
    statement = select(UserWatchlistItem).where(UserWatchlistItem.ts_code == ts_code)
    rows = (await session.execute(statement)).scalars().all()
    for row in rows:
        if row.daily_analysis_enabled:
            row.last_daily_analysis_at = analyzed_at


async def has_daily_watchlist_report_for_date(
    session: AsyncSession,
    *,
    ts_code: str,
    target_date: date,
) -> bool:
    statement = (
        select(AnalysisReport)
        .where(AnalysisReport.ts_code == ts_code)
        .where(AnalysisReport.trigger_source == "watchlist_daily")
        .order_by(AnalysisReport.generated_at.desc())
        .limit(1)
    )
    report = (await session.execute(statement)).scalar_one_or_none()
    if report is None or report.generated_at is None:
        return False

    report_generated_at = report.generated_at
    if report_generated_at.tzinfo is None:
        report_generated_at = report_generated_at.replace(tzinfo=UTC)
    return report_generated_at.date() == target_date


async def is_trade_day(
    session: AsyncSession,
    *,
    target_date: date,
    exchange: str = "SSE",
) -> bool:
    calendar = await session.get(StockTradeCalendar, (exchange, target_date))
    if calendar is not None:
        return calendar.is_open == "1"

    # 降级分支：交易日历缺失时退化为工作日判断，避免 Worker 因基础表未同步而完全停摆。
    return target_date.weekday() < 5


def should_run_hourly(now: datetime) -> bool:
    return now.minute == 5


def should_run_daily(now: datetime) -> bool:
    return now.hour == 18 and now.minute == 10


async def _load_watch_snapshot_payload(
    session: AsyncSession,
    *,
    ts_code: str,
) -> dict[str, object] | None:
    settings = get_settings()

    try:
        gateway = TushareGateway(settings.tushare_token)
        end_date = datetime.now(UTC).strftime("%Y%m%d")
        start_date = (datetime.now(UTC) - timedelta(days=14)).strftime("%Y%m%d")
        rows = await gateway.fetch_daily_by_range(
            ts_code=ts_code,
            start_date=start_date,
            end_date=end_date,
        )
    except Exception:
        rows = []

    if rows:
        sorted_rows = sorted(
            rows,
            key=lambda item: str(item.get("trade_date") or ""),
            reverse=True,
        )
        latest = sorted_rows[0]
        return {
            "ts_code": ts_code,
            "trade_date": latest.get("trade_date"),
            "open": latest.get("open"),
            "high": latest.get("high"),
            "low": latest.get("low"),
            "close": latest.get("close"),
            "pre_close": latest.get("pre_close"),
            "change": latest.get("change"),
            "pct_chg": latest.get("pct_chg"),
            "vol": latest.get("vol"),
            "amount": latest.get("amount"),
            "source": "tushare_daily",
        }

    statement = (
        select(StockDailySnapshot)
        .where(StockDailySnapshot.ts_code == ts_code)
        .order_by(StockDailySnapshot.trade_date.desc())
        .limit(1)
    )
    snapshot = (await session.execute(statement)).scalar_one_or_none()
    if snapshot is None:
        return None

    return {
        "ts_code": snapshot.ts_code,
        "trade_date": snapshot.trade_date.isoformat(),
        "open": float(snapshot.open) if snapshot.open is not None else None,
        "high": float(snapshot.high) if snapshot.high is not None else None,
        "low": float(snapshot.low) if snapshot.low is not None else None,
        "close": float(snapshot.close) if snapshot.close is not None else None,
        "pre_close": (
            float(snapshot.pre_close) if snapshot.pre_close is not None else None
        ),
        "change": float(snapshot.change) if snapshot.change is not None else None,
        "pct_chg": float(snapshot.pct_chg) if snapshot.pct_chg is not None else None,
        "vol": float(snapshot.vol) if snapshot.vol is not None else None,
        "amount": float(snapshot.amount) if snapshot.amount is not None else None,
        "source": "stock_daily_snapshots",
    }


async def sync_stock_watch_context(
    *,
    session: AsyncSession,
    ts_code: str,
    now: datetime,
) -> None:
    instrument = await session.get(StockInstrument, ts_code)
    if instrument is None:
        raise ValueError(f"stock instrument not found: {ts_code}")

    symbol = (instrument.symbol or "").strip()
    if not symbol:
        raise ValueError(f"stock symbol not found: {ts_code}")

    # 关键流程：小时同步统一把新闻和公告落入 news_events，后续分析接口直接复用同一事件池。
    stock_news_rows = await fetch_stock_news(symbol)
    mapped_news = map_stock_news_rows(
        ts_code=ts_code,
        symbol=symbol,
        rows=stock_news_rows,
    )

    try:
        announcement_rows = await fetch_stock_announcements(symbol=symbol)
    except Exception:
        announcement_rows = []

    mapped_announcements = map_stock_announcement_rows(
        ts_code=ts_code,
        symbol=symbol,
        rows=announcement_rows,
    )
    merged_items = [*mapped_news, *mapped_announcements]
    merged_items.sort(
        key=lambda item: item.published_at or datetime.min.replace(tzinfo=UTC),
        reverse=True,
    )

    await replace_stock_news_rows(
        session=session,
        ts_code=ts_code,
        symbol=symbol,
        cache_variant="with_announcements",
        fetched_at=now,
        rows=merged_items,
    )

    snapshot_payload = await _load_watch_snapshot_payload(session, ts_code=ts_code)
    session.add(
        StockWatchSnapshot(
            ts_code=ts_code,
            captured_at=now,
            source="worker",
            payload_json=snapshot_payload,
        )
    )
    await session.commit()


async def run_hourly_watchlist_sync(
    session: AsyncSession,
    *,
    now: datetime,
    sync_stock_watch_context: Callable[..., Awaitable[None]] = sync_stock_watch_context,
) -> dict[str, int]:
    processed = 0
    skipped = 0

    for ts_code in await list_hourly_sync_targets(session):
        try:
            await sync_stock_watch_context(session=session, ts_code=ts_code, now=now)
            await mark_hourly_sync_completed(session, ts_code=ts_code, synced_at=now)
            await session.commit()
            processed += 1
        except Exception:
            await session.rollback()
            skipped += 1

    return {"processed": processed, "skipped": skipped}


async def run_daily_watchlist_analysis(
    session: AsyncSession,
    *,
    now: datetime,
    start_analysis_session_fn: Callable[..., Awaitable[dict[str, object]]] = start_analysis_session,
    execute_inline: bool = True,
) -> dict[str, int]:
    processed = 0
    skipped = 0

    for target in await list_daily_analysis_targets(session):
        if await has_daily_watchlist_report_for_date(
            session,
            ts_code=target.ts_code,
            target_date=now.date(),
        ):
            await mark_daily_analysis_completed(
                session,
                ts_code=target.ts_code,
                analyzed_at=now,
            )
            await session.commit()
            skipped += 1
            continue

        try:
            await start_analysis_session_fn(
                session,
                target.ts_code,
                topic=None,
                force_refresh=False,
                use_web_search=target.use_web_search,
                trigger_source="watchlist_daily",
                execute_inline=execute_inline,
            )
            await mark_daily_analysis_completed(
                session,
                ts_code=target.ts_code,
                analyzed_at=now,
            )
            await session.commit()
            processed += 1
        except Exception:
            await session.rollback()
            skipped += 1

    return {"processed": processed, "skipped": skipped}
