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
    return '"' + identifier.replace('"', '""') + '"'


async def ensure_database_exists(
    settings: Settings,
    connector: Callable[..., Awaitable[asyncpg.Connection]] = asyncpg.connect,
) -> None:
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
    async with target_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


async def ensure_database_schema() -> None:
    settings = get_settings()
    if settings.db_auto_create_database:
        await ensure_database_exists(settings)

    await ensure_postgres_schema_exists(settings)

    await ensure_schema_for_engine(engine)
    logger.info(
        "event=db.schema.ensure.success tables=%s",
        ",".join(sorted(Base.metadata.tables.keys())),
    )
