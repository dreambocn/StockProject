from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import Column, MetaData, String, Table, inspect as sa_inspect, pool, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import async_engine_from_config

import app.models  # noqa: F401
from app.db.base import Base
from app.db.migrations import build_alembic_config


config = context.config
runtime_config = build_alembic_config(config.get_main_option("sqlalchemy.url") or None)
config.set_main_option("script_location", runtime_config.get_main_option("script_location"))
config.set_main_option("sqlalchemy.url", runtime_config.get_main_option("sqlalchemy.url"))

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
BASELINE_REVISION = "20260331_0001"
LEGACY_SCHEMA_MARKER_TABLES = {
    "users",
    "stock_instruments",
    "analysis_reports",
    "analysis_generation_sessions",
    "news_fetch_batches",
}


def _stamp_legacy_schema_baseline(connection) -> None:
    inspector = sa_inspect(connection)
    table_names = set(inspector.get_table_names())
    if not table_names or not table_names.intersection(LEGACY_SCHEMA_MARKER_TABLES):
        return

    version_table = Table(
        "alembic_version",
        MetaData(),
        Column("version_num", String(length=32), nullable=False, primary_key=True),
    )
    version_table.create(connection, checkfirst=True)
    current_version = connection.execute(
        text("SELECT version_num FROM alembic_version")
    ).scalar_one_or_none()
    if current_version:
        return

    # 兼容 Alembic 引入前已存在的旧库：若核心表已存在但没有版本表，则先标记到 baseline。
    connection.execute(
        version_table.insert().values(version_num=BASELINE_REVISION)
    )


def _ensure_version_row(connection, revision: str | tuple[str, ...] | None) -> None:
    if revision is None:
        return

    resolved_revision = revision[0] if isinstance(revision, tuple) else revision
    if not resolved_revision:
        return

    try:
        current_version = connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one_or_none()
    except SQLAlchemyError:
        return

    if current_version:
        return

    connection.execute(
        text("INSERT INTO alembic_version (version_num) VALUES (:version_num)"),
        {"version_num": resolved_revision},
    )


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        destination_revision = context.get_revision_argument()
        await connection.run_sync(_stamp_legacy_schema_baseline)
        if connection.in_transaction():
            await connection.commit()
        await connection.run_sync(do_run_migrations)
        await connection.run_sync(
            lambda sync_conn: _ensure_version_row(sync_conn, destination_revision)
        )
        if connection.in_transaction():
            await connection.commit()

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    import asyncio

    asyncio.run(run_migrations_online())
