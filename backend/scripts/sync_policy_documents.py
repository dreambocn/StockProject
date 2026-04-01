import asyncio
import sys
from pathlib import Path

# 直接执行脚本时把 backend 根目录加入模块搜索路径，避免 `app.*` 导入失败。
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.logging import get_logger, setup_logging
from app.db.init_db import ensure_database_schema
from app.db.session import SessionLocal
from app.services.policy_sync_service import sync_policy_documents


LOGGER = get_logger(__name__)


async def main() -> None:
    setup_logging()
    LOGGER.info("event=policy_sync_script_starting message=政策同步脚本启动")
    await ensure_database_schema()

    async with SessionLocal() as session:
        result = await sync_policy_documents(
            session,
            trigger_source="script.policy.sync",
            force_refresh=True,
        )
        LOGGER.info(
            "event=policy_sync_script_finished inserted_count=%s updated_count=%s deduped_count=%s failed_provider_count=%s message=政策同步脚本执行完成",
            result["inserted_count"],
            result["updated_count"],
            result["deduped_count"],
            result["failed_provider_count"],
        )


if __name__ == "__main__":
    asyncio.run(main())
