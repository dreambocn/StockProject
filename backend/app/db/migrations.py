import asyncio
import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.settings import get_settings


BACKEND_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI_PATH = BACKEND_ROOT / "alembic.ini"
ALEMBIC_SCRIPT_LOCATION = BACKEND_ROOT / "alembic"
MIGRATION_DATABASE_URL_ENV = "DATABASE_URL_FOR_MIGRATIONS"


def build_alembic_config(database_url: str | None = None) -> Config:
    config = Config(str(ALEMBIC_INI_PATH))
    # 显式写入绝对路径，避免从不同 cwd 执行时找不到迁移目录。
    config.set_main_option("script_location", str(ALEMBIC_SCRIPT_LOCATION))
    resolved_database_url = (
        database_url
        or os.getenv(MIGRATION_DATABASE_URL_ENV)
        or get_settings().postgres_async_dsn
    )
    config.set_main_option("sqlalchemy.url", resolved_database_url)
    return config


def get_expected_migration_heads(config: Config | None = None) -> set[str]:
    resolved_config = config or build_alembic_config()
    script_directory = ScriptDirectory.from_config(resolved_config)
    return set(script_directory.get_heads())


async def run_database_migrations(
    *,
    config: Config | None = None,
    revision: str = "head",
) -> None:
    resolved_config = config or build_alembic_config()
    await asyncio.to_thread(command.upgrade, resolved_config, revision)


async def validate_database_schema(
    *,
    target_engine: AsyncEngine,
    config: Config | None = None,
) -> None:
    resolved_config = config or build_alembic_config()
    expected_heads = get_expected_migration_heads(resolved_config)

    async with target_engine.connect() as connection:
        try:
            result = await connection.execute(text("SELECT version_num FROM alembic_version"))
        except SQLAlchemyError as exc:
            raise RuntimeError("数据库尚未执行迁移，请先运行 alembic upgrade head。") from exc

        current_revisions = {item for item in result.scalars().all() if item}

    if not current_revisions:
        raise RuntimeError("数据库迁移版本为空，请先运行 alembic upgrade head。")

    if current_revisions != expected_heads:
        raise RuntimeError(
            "数据库迁移版本不是最新版本，请先运行 alembic upgrade head。"
        )
