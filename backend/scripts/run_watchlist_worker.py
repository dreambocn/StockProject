import asyncio
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# 直接执行脚本时把 backend 根目录加入模块搜索路径，避免 `app.*` 导入失败。
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.logging import get_logger, setup_logging
from app.db.init_db import ensure_database_schema
from app.db.session import SessionLocal
from app.services.watchlist_worker_service import (
    is_trade_day,
    run_daily_watchlist_analysis,
    run_hourly_watchlist_sync,
    should_run_daily,
    should_run_hourly,
)


LOGGER = get_logger(__name__)
HONG_KONG_TZ = ZoneInfo("Asia/Hong_Kong")
POLL_INTERVAL_SECONDS = 30


async def _run_once(
    *,
    now: datetime,
    hourly_marker: str | None,
    daily_marker: str | None,
) -> tuple[str | None, str | None]:
    next_hourly_marker = hourly_marker
    next_daily_marker = daily_marker

    async with SessionLocal() as session:
        if should_run_hourly(now):
            current_hourly_marker = now.strftime("%Y%m%d%H")
            if current_hourly_marker != hourly_marker:
                result = await run_hourly_watchlist_sync(session, now=now)
                LOGGER.info(
                    "event=watchlist_hourly_sync processed=%s skipped=%s now=%s",
                    result["processed"],
                    result["skipped"],
                    now.isoformat(),
                )
                next_hourly_marker = current_hourly_marker

        if should_run_daily(now):
            current_daily_marker = now.strftime("%Y%m%d")
            if current_daily_marker != daily_marker:
                if await is_trade_day(session, target_date=now.date()):
                    result = await run_daily_watchlist_analysis(session, now=now)
                    LOGGER.info(
                        "event=watchlist_daily_analysis processed=%s skipped=%s now=%s",
                        result["processed"],
                        result["skipped"],
                        now.isoformat(),
                    )
                else:
                    LOGGER.info(
                        "event=watchlist_daily_analysis_skipped reason=non_trade_day now=%s",
                        now.isoformat(),
                    )
                next_daily_marker = current_daily_marker

    return next_hourly_marker, next_daily_marker


async def main() -> None:
    setup_logging()
    LOGGER.info("event=watchlist_worker_starting timezone=%s", HONG_KONG_TZ.key)
    await ensure_database_schema()

    hourly_marker: str | None = None
    daily_marker: str | None = None

    while True:
        try:
            now = datetime.now(HONG_KONG_TZ).replace(second=0, microsecond=0)
            hourly_marker, daily_marker = await _run_once(
                now=now,
                hourly_marker=hourly_marker,
                daily_marker=daily_marker,
            )
        except Exception:
            LOGGER.exception("event=watchlist_worker_iteration_failed")

        await asyncio.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    asyncio.run(main())
