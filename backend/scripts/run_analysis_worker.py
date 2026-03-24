import asyncio
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

# 直接执行脚本时把 backend 根目录加入模块搜索路径，避免 `app.*` 导入失败。
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.logging import get_logger, setup_logging
from app.core.settings import get_settings
from app.db.init_db import ensure_database_schema
from app.db.session import SessionLocal
from app.services.analysis_repository import claim_next_analysis_session_for_worker
from app.services.analysis_service import run_analysis_session_by_id


LOGGER = get_logger(__name__)


async def run_analysis_worker_iteration() -> str | None:
    settings = get_settings()
    stale_before = datetime.now(UTC) - timedelta(
        seconds=settings.analysis_running_stale_seconds
    )

    async with SessionLocal() as session:
        claimed_session_id = await claim_next_analysis_session_for_worker(
            session,
            stale_before=stale_before,
        )
        await session.commit()

    if claimed_session_id is None:
        return None

    LOGGER.info(
        "event=analysis_worker_session_claimed session_id=%s message=已领取分析会话",
        claimed_session_id,
    )
    await run_analysis_session_by_id(claimed_session_id)
    return claimed_session_id


async def main() -> None:
    setup_logging()
    settings = get_settings()
    poll_interval_seconds = max(1, settings.analysis_worker_poll_interval_seconds)

    LOGGER.info(
        "event=analysis_worker_starting poll_interval_seconds=%s stale_seconds=%s message=分析Worker启动",
        poll_interval_seconds,
        settings.analysis_running_stale_seconds,
    )
    await ensure_database_schema()

    while True:
        try:
            claimed_session_id = await run_analysis_worker_iteration()
            if claimed_session_id is None:
                LOGGER.debug("event=analysis_worker_idle message=当前无可执行分析会话")
        except Exception:
            LOGGER.exception("event=analysis_worker_iteration_failed message=分析Worker轮询失败")

        await asyncio.sleep(poll_interval_seconds)


if __name__ == "__main__":
    asyncio.run(main())
