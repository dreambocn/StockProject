from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
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
from app.models.system_job_run import SystemJobRun
from app.models.stock_watch_snapshot import StockWatchSnapshot
from app.models.user_watchlist_item import UserWatchlistItem
from app.services.analysis_service import start_analysis_session
from app.services.candidate_evidence_service import refresh_candidate_evidence_caches
from app.services.job_service import (
    JOB_STATUS_FAILED,
    JOB_STATUS_RUNNING,
    JOB_STATUS_SUCCESS,
    create_job_run,
    finish_job_run,
)
from app.services.news_fetch_batch_service import (
    NEWS_FETCH_STATUS_FAILED,
    NEWS_FETCH_STATUS_PARTIAL,
    NEWS_FETCH_STATUS_SUCCESS,
    create_news_fetch_batch,
    finalize_news_fetch_batch,
)
from app.services.news_mapper_service import (
    map_stock_announcement_rows,
    map_stock_news_rows,
)
from app.services.news_repository import replace_stock_news_rows


logger = get_logger(__name__)


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
        # 同一标的有多个自选项时，只要任一开启 web_search 就视为需要。
        if row.web_search_enabled:
            current.use_web_search = True

    return sorted(aggregated.values(), key=lambda item: item.ts_code)


async def mark_hourly_sync_completed(
    session: AsyncSession,
    *,
    ts_code: str,
    synced_at: datetime,
) -> None:
    # 只更新开启小时同步的自选项，避免影响关闭同步的记录。
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
    # 每日分析完成仅标记开关为真的项，防止误写其他配置。
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
    # 以报告生成日期为判断基准，避免同日重复触发生成。
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
    except Exception as exc:
        logger.warning(
            "event=watchlist_snapshot_fetch_degraded ts_code=%s stage=%s error_type=%s message=快照回源失败，回退本地快照",
            ts_code,
            "snapshot",
            type(exc).__name__,
        )
        rows = []

    if rows:
        # 优先使用三方日线数据，保证快照反映最新市场行情。
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

    # 回退到本地快照时做显式类型转换，统一为可序列化的 float/str。
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

    batch = await create_news_fetch_batch(
        session,
        scope="stock",
        cache_variant="with_announcements",
        ts_code=ts_code,
        trigger_source="worker.watchlist.hourly",
        fetched_at=now,
        started_at=now,
    )
    provider_stats: list[dict[str, object]] = []
    degrade_reasons: list[str] = []

    # 关键流程：小时同步统一把新闻和公告落入 news_events，后续分析接口直接复用同一事件池。
    try:
        stock_news_rows = await fetch_stock_news(symbol)
        provider_stats.append(
            {
                "provider": "eastmoney_stock",
                "status": "success",
                "error_type": None,
                "raw_count": len(stock_news_rows),
                "mapped_count": 0,
                "persisted_count": 0,
            }
        )
    except Exception as exc:
        # 关键降级：新闻抓取失败时回退为空列表，保证小时同步链路不断。
        logger.warning(
            "event=watchlist_news_fetch_degraded ts_code=%s stage=%s error_type=%s message=新闻抓取失败，回退为空列表",
            ts_code,
            "news",
            type(exc).__name__,
        )
        stock_news_rows = []
        provider_stats.append(
            {
                "provider": "eastmoney_stock",
                "status": "failed",
                "error_type": type(exc).__name__,
                "raw_count": 0,
                "mapped_count": 0,
                "persisted_count": 0,
            }
        )
        degrade_reasons.append("stock.news_failed")
    mapped_news = map_stock_news_rows(
        ts_code=ts_code,
        symbol=symbol,
        rows=stock_news_rows,
    )
    provider_stats[0]["mapped_count"] = len(mapped_news)
    provider_stats[0]["persisted_count"] = len(mapped_news)

    try:
        announcement_rows = await fetch_stock_announcements(symbol=symbol)
        provider_stats.append(
            {
                "provider": "cninfo_announcement",
                "status": "success",
                "error_type": None,
                "raw_count": len(announcement_rows),
                "mapped_count": 0,
                "persisted_count": 0,
            }
        )
    except Exception as exc:
        # 关键降级：公告抓取失败时回退为空列表，避免中断后续入库与快照归档。
        logger.warning(
            "event=watchlist_news_fetch_degraded ts_code=%s stage=%s error_type=%s message=公告抓取失败，回退为空列表",
            ts_code,
            "announcement",
            type(exc).__name__,
        )
        announcement_rows = []
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

    mapped_announcements = map_stock_announcement_rows(
        ts_code=ts_code,
        symbol=symbol,
        rows=announcement_rows,
    )
    provider_stats[1]["mapped_count"] = len(mapped_announcements)
    provider_stats[1]["persisted_count"] = len(mapped_announcements)
    merged_items = [*mapped_news, *mapped_announcements]
    merged_items.sort(
        key=lambda item: item.published_at or datetime.min.replace(tzinfo=UTC),
        reverse=True,
    )

    if merged_items:
        await replace_stock_news_rows(
            session=session,
            ts_code=ts_code,
            symbol=symbol,
            cache_variant="with_announcements",
            fetched_at=now,
            batch_id=batch.id,
            rows=merged_items,
        )

    await finalize_news_fetch_batch(
        session,
        batch=batch,
        status=(
            NEWS_FETCH_STATUS_FAILED
            if not merged_items
            else (
                NEWS_FETCH_STATUS_PARTIAL
                if degrade_reasons
                else NEWS_FETCH_STATUS_SUCCESS
            )
        ),
        finished_at=now,
        row_count_raw=sum(int(item["raw_count"]) for item in provider_stats),
        row_count_mapped=len(merged_items),
        row_count_persisted=len(merged_items),
        provider_stats=provider_stats,
        degrade_reasons=degrade_reasons or (
            ["mapping.empty_after_filter"] if not merged_items else []
        ),
        error_type=None,
        error_message=(
            "小时同步未获取到可持久化新闻，已仅保留快照归档"
            if not merged_items
            else None
        ),
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
    refresh_candidate_evidence_caches_fn: Callable[..., Awaitable[dict[str, int]]] | None = None,
) -> dict[str, int]:
    processed = 0
    skipped = 0
    if refresh_candidate_evidence_caches_fn is not None:
        settings = get_settings()
        include_research_report = (
            settings.candidate_research_refresh_interval_hours > 0
            and now.hour % settings.candidate_research_refresh_interval_hours == 0
        )

        try:
            # 关键流程：热点页的候选证据由后台小时任务预刷新，前台请求只读 Redis/DB，
            # 避免用户首屏直接触发东方财富全市场研报分页抓取。
            refresh_result = await refresh_candidate_evidence_caches_fn(
                session=session,
                now=now,
                include_research_report=include_research_report,
            )
            logger.info(
                "event=candidate_evidence_refresh_completed hot_search_rows=%s research_report_rows=%s include_research_report=%s now=%s",
                refresh_result["hot_search_rows"],
                refresh_result["research_report_rows"],
                include_research_report,
                now.isoformat(),
            )
        except Exception as exc:
            await session.rollback()
            # 降级分支：候选证据刷新失败不应阻断 watchlist 小时同步，避免后台任务互相拖死。
            logger.warning(
                "event=candidate_evidence_refresh_failed stage=%s error_type=%s message=候选证据定时刷新失败，继续执行自选股小时同步",
                "hourly_prefetch",
                type(exc).__name__,
                exc_info=exc,
            )

    for ts_code in await list_hourly_sync_targets(session):
        watch_job = await create_job_run(
            session,
            job_type="watchlist_hourly_sync",
            status=JOB_STATUS_RUNNING,
            trigger_source="worker.watchlist.hourly",
            resource_type="stock",
            resource_key=ts_code,
            summary="自选股小时同步执行中",
            payload_json={
                "ts_code": ts_code,
                "run_at": now.isoformat(),
            },
        )
        watch_job_id = watch_job.id
        await session.commit()
        try:
            await sync_stock_watch_context(session=session, ts_code=ts_code, now=now)
            await mark_hourly_sync_completed(session, ts_code=ts_code, synced_at=now)
            await finish_job_run(
                session,
                job=watch_job,
                status=JOB_STATUS_SUCCESS,
                summary="自选股小时同步完成",
                metrics_json={
                    "ts_code": ts_code,
                    "processed": 1,
                    "skipped": 0,
                },
            )
            await session.commit()
            processed += 1
        except Exception as exc:
            await session.rollback()
            watch_job = await session.get(SystemJobRun, watch_job_id)
            if watch_job is not None:
                await finish_job_run(
                    session,
                    job=watch_job,
                    status=JOB_STATUS_FAILED,
                    summary="自选股小时同步失败",
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                    metrics_json={
                        "ts_code": ts_code,
                        "processed": 0,
                        "skipped": 1,
                    },
                )
                await session.commit()
            # 降级分支：单只股票小时同步失败时仅跳过该项，避免一次异常阻断整批任务。
            logger.warning(
                "event=watchlist_item_sync_failed ts_code=%s stage=%s error_type=%s message=小时同步失败",
                ts_code,
                "hourly_sync",
                type(exc).__name__,
                exc_info=exc,
            )
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
        watch_job = await create_job_run(
            session,
            job_type="watchlist_daily_analysis",
            status=JOB_STATUS_RUNNING,
            trigger_source="worker.watchlist.daily",
            resource_type="stock",
            resource_key=target.ts_code,
            summary="自选股日分析任务执行中",
            payload_json={
                "ts_code": target.ts_code,
                "run_date": now.date().isoformat(),
                "use_web_search": target.use_web_search,
            },
        )
        watch_job_id = watch_job.id
        await session.commit()
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
            await finish_job_run(
                session,
                job=watch_job,
                status=JOB_STATUS_SUCCESS,
                summary="当日已存在日报，跳过重复生成",
                metrics_json={
                    "ts_code": target.ts_code,
                    "processed": 0,
                    "skipped": 1,
                    "skip_reason": "report_exists",
                },
            )
            await session.commit()
            skipped += 1
            continue

        try:
            analysis_result = await start_analysis_session_fn(
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
            await finish_job_run(
                session,
                job=watch_job,
                status=JOB_STATUS_SUCCESS,
                summary="自选股日分析任务完成",
                linked_entity_type=(
                    "analysis_generation_session"
                    if analysis_result.get("session_id")
                    else None
                ),
                linked_entity_id=(
                    str(analysis_result.get("session_id"))
                    if analysis_result.get("session_id")
                    else None
                ),
                metrics_json={
                    "ts_code": target.ts_code,
                    "processed": 1,
                    "skipped": 0,
                    "cached": bool(analysis_result.get("cached")),
                    "reused": bool(analysis_result.get("reused")),
                },
            )
            await session.commit()
            processed += 1
        except Exception as exc:
            await session.rollback()
            watch_job = await session.get(SystemJobRun, watch_job_id)
            if watch_job is not None:
                await finish_job_run(
                    session,
                    job=watch_job,
                    status=JOB_STATUS_FAILED,
                    summary="自选股日分析任务失败",
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                    metrics_json={
                        "ts_code": target.ts_code,
                        "processed": 0,
                        "skipped": 1,
                    },
                )
                await session.commit()
            # 降级分支：单只股票每日报告失败时继续处理后续标的，统计语义保持不变。
            logger.warning(
                "event=watchlist_item_analysis_failed ts_code=%s stage=%s error_type=%s message=每日报告分析失败",
                target.ts_code,
                "daily_analysis",
                type(exc).__name__,
                exc_info=exc,
            )
            skipped += 1

    return {"processed": processed, "skipped": skipped}
