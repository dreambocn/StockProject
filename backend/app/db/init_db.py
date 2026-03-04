from collections.abc import Callable, Awaitable

import asyncpg
from sqlalchemy.ext.asyncio import AsyncEngine

import app.models  # noqa: F401
from app.core.logging import get_logger
from app.core.settings import Settings, get_settings
from app.db.base import Base
from app.db.session import engine


logger = get_logger("app.db")


def _quote_identifier(identifier: str) -> str:
    # 对数据库/Schema 名做安全转义，避免拼接 DDL 时注入风险。
    return '"' + identifier.replace('"', '""') + '"'


async def ensure_database_exists(
    settings: Settings,
    connector: Callable[..., Awaitable[asyncpg.Connection]] = asyncpg.connect,
) -> None:
    # 使用维护库连接检查目标库是否存在，缺失时自动创建。
    connection = await connector(
        host=settings.postgres_host,
        port=settings.postgres_port,
        user=settings.postgres_user,
        password=settings.postgres_password,
        database=settings.postgres_maintenance_db,
    )

    try:
        rows = await connection.fetch("select datname from pg_database")
        existing = {str(row["datname"]) for row in rows}
        if settings.postgres_database in existing:
            return

        database_identifier = _quote_identifier(settings.postgres_database)
        await connection.execute(f"create database {database_identifier}")
        logger.info(
            "event=db.database.ensure.created db=%s", settings.postgres_database
        )
    finally:
        await connection.close()


async def ensure_postgres_schema_exists(
    settings: Settings,
    connector: Callable[..., Awaitable[asyncpg.Connection]] = asyncpg.connect,
) -> None:
    # 若未配置 schema，则沿用数据库默认 search_path。
    if not settings.postgres_schema:
        return

    connection = await connector(
        host=settings.postgres_host,
        port=settings.postgres_port,
        user=settings.postgres_user,
        password=settings.postgres_password,
        database=settings.postgres_database,
    )

    try:
        schema_exists = await connection.fetchval(
            "select 1 from information_schema.schemata where schema_name = $1",
            settings.postgres_schema,
        )
        if schema_exists:
            return

        schema_identifier = _quote_identifier(settings.postgres_schema)
        await connection.execute(f"create schema {schema_identifier}")
        logger.info(
            "event=db.schema.ensure.created schema=%s", settings.postgres_schema
        )
    finally:
        await connection.close()


async def ensure_schema_for_engine(target_engine: AsyncEngine) -> None:
    # 统一通过 SQLAlchemy 元数据建表，保证模型与表结构同步。
    async with target_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


async def ensure_database_schema() -> None:
    settings = get_settings()
    if settings.db_auto_create_database:
        # 先保证数据库存在，再进行 schema 与表初始化，避免后续步骤失败。
        await ensure_database_exists(settings)

    await ensure_postgres_schema_exists(settings)

    await ensure_schema_for_engine(engine)
    logger.info(
        "event=db.schema.ensure.success tables=%s",
        ",".join(sorted(Base.metadata.tables.keys())),
    )
