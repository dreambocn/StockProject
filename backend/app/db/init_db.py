from collections.abc import Callable, Awaitable

import asyncpg
from sqlalchemy import inspect, or_, select, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

import app.models  # noqa: F401
from app.core.logging import get_logger
from app.core.security import hash_password
from app.core.settings import Settings, get_settings
from app.db.base import Base
from app.db.migrations import (
    run_database_migrations,
    validate_database_schema as validate_database_schema_revision,
)
from app.db.session import SessionLocal, engine
from app.models.user import USER_LEVEL_ADMIN, User


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

        # 关键流程：对历史库执行最小列补齐，避免 create_all 不会自动 ALTER 导致运行期写入失败。
        # 这里仅补齐必需列与索引，不改变既有数据契约。
        await connection.run_sync(_ensure_stock_instrument_columns)
        await connection.run_sync(_ensure_news_fetch_batch_columns)
        await connection.run_sync(_ensure_news_fetch_batch_indexes)
        await connection.run_sync(_ensure_news_event_columns)
        await connection.run_sync(_ensure_news_event_indexes)
        await connection.run_sync(_ensure_analysis_report_columns)
        await connection.run_sync(_ensure_stock_candidate_evidence_cache_columns)


def _ensure_stock_instrument_columns(sync_connection: Connection) -> None:
    inspector = inspect(sync_connection)
    if "stock_instruments" not in set(inspector.get_table_names()):
        return

    existing_columns = {
        item["name"] for item in inspector.get_columns("stock_instruments")
    }
    required_column_sql: dict[str, str] = {
        "fullname": "VARCHAR(128)",
        "enname": "VARCHAR(256)",
        "cnspell": "VARCHAR(32)",
        "curr_type": "VARCHAR(8)",
        "act_name": "VARCHAR(128)",
        "act_ent_type": "VARCHAR(64)",
    }
    for column_name, column_type in required_column_sql.items():
        if column_name in existing_columns:
            continue
        sync_connection.execute(
            text(
                f"ALTER TABLE stock_instruments ADD COLUMN {column_name} {column_type}"
            )
        )


def _ensure_news_event_columns(sync_connection: Connection) -> None:
    inspector = inspect(sync_connection)
    if "news_events" not in set(inspector.get_table_names()):
        return

    existing_columns = {
        item["name"] for item in inspector.get_columns("news_events")
    }
    required_column_sql: dict[str, str] = {
        "event_type": "VARCHAR(32)",
        "sentiment_label": "VARCHAR(16)",
        "sentiment_score": "NUMERIC(12, 6)",
        "event_tags": "TEXT",
        "analysis_status": "VARCHAR(16)",
        "provider": "VARCHAR(32) DEFAULT 'internal'",
        "external_id": "VARCHAR(128)",
        "cluster_key": "VARCHAR(255)",
        "source_priority": "INTEGER DEFAULT 0",
        "evidence_kind": "VARCHAR(32) DEFAULT 'hot'",
        "batch_id": "VARCHAR(36)",
    }
    for column_name, column_type in required_column_sql.items():
        if column_name in existing_columns:
            continue
        sync_connection.execute(
            text(
                f"ALTER TABLE news_events ADD COLUMN {column_name} {column_type}"
            )
        )


def _ensure_news_event_indexes(sync_connection: Connection) -> None:
    inspector = inspect(sync_connection)
    if "news_events" not in set(inspector.get_table_names()):
        return

    # 查询维度以 scope/ts_code/cluster_key 为主，索引用于保障新闻检索与去重性能。
    index_sql = (
        "CREATE INDEX IF NOT EXISTS ix_news_events_scope_cache_variant_fetched_at "
        "ON news_events (scope, cache_variant, fetched_at)",
        "CREATE INDEX IF NOT EXISTS ix_news_events_scope_ts_code_cache_variant_fetched_at "
        "ON news_events (scope, ts_code, cache_variant, fetched_at)",
        "CREATE INDEX IF NOT EXISTS ix_news_events_scope_cluster_key_fetched_at "
        "ON news_events (scope, cluster_key, fetched_at)",
        "CREATE INDEX IF NOT EXISTS ix_news_events_batch_id "
        "ON news_events (batch_id)",
        "CREATE INDEX IF NOT EXISTS ix_news_events_scope_topic_published_fetched_created "
        "ON news_events (scope, macro_topic, published_at, fetched_at, created_at)",
        "CREATE INDEX IF NOT EXISTS ix_news_events_scope_ts_code_published_fetched_created "
        "ON news_events (scope, ts_code, published_at, fetched_at, created_at)",
    )
    for statement in index_sql:
        sync_connection.execute(text(statement))


def _ensure_news_fetch_batch_columns(sync_connection: Connection) -> None:
    inspector = inspect(sync_connection)
    if "news_fetch_batches" not in set(inspector.get_table_names()):
        return

    existing_columns = {
        item["name"] for item in inspector.get_columns("news_fetch_batches")
    }
    required_column_sql: dict[str, str] = {
        "scope": "VARCHAR(16)",
        "cache_variant": "VARCHAR(32)",
        "ts_code": "VARCHAR(12)",
        "trigger_source": "VARCHAR(32)",
        "status": "VARCHAR(16)",
        "started_at": "TIMESTAMP",
        "finished_at": "TIMESTAMP",
        "fetched_at": "TIMESTAMP",
        "duration_ms": "INTEGER",
        "row_count_raw": "INTEGER DEFAULT 0",
        "row_count_mapped": "INTEGER DEFAULT 0",
        "row_count_persisted": "INTEGER DEFAULT 0",
        "provider_stats_json": "JSON",
        "degrade_reasons_json": "JSON",
        "error_type": "VARCHAR(64)",
        "error_message": "TEXT",
    }
    for column_name, column_type in required_column_sql.items():
        if column_name in existing_columns:
            continue
        sync_connection.execute(
            text(
                "ALTER TABLE news_fetch_batches "
                f"ADD COLUMN {column_name} {column_type}"
            )
        )


def _ensure_news_fetch_batch_indexes(sync_connection: Connection) -> None:
    inspector = inspect(sync_connection)
    if "news_fetch_batches" not in set(inspector.get_table_names()):
        return

    # 批次检索常以范围与状态聚合，索引优先覆盖后台任务监控与管理台筛选。
    index_sql = (
        "CREATE INDEX IF NOT EXISTS ix_news_fetch_batches_scope_cache_variant_fetched_at "
        "ON news_fetch_batches (scope, cache_variant, fetched_at)",
        "CREATE INDEX IF NOT EXISTS ix_news_fetch_batches_scope_ts_code_cache_variant_fetched_at "
        "ON news_fetch_batches (scope, ts_code, cache_variant, fetched_at)",
        "CREATE INDEX IF NOT EXISTS ix_news_fetch_batches_status_finished_at "
        "ON news_fetch_batches (status, finished_at)",
        "CREATE INDEX IF NOT EXISTS ix_news_fetch_batches_trigger_source_finished_at "
        "ON news_fetch_batches (trigger_source, finished_at)",
    )
    for statement in index_sql:
        sync_connection.execute(text(statement))


def _ensure_analysis_report_columns(sync_connection: Connection) -> None:
    inspector = inspect(sync_connection)
    if "analysis_reports" not in set(inspector.get_table_names()):
        return

    existing_columns = {
        item["name"] for item in inspector.get_columns("analysis_reports")
    }
    required_column_sql: dict[str, str] = {
        "trigger_source": "VARCHAR(32) DEFAULT 'manual'",
        "used_web_search": "BOOLEAN DEFAULT FALSE",
        "web_search_status": "VARCHAR(16) DEFAULT 'disabled'",
        "session_id": "VARCHAR(36)",
        "started_at": "TIMESTAMP",
        "completed_at": "TIMESTAMP",
        "content_format": "VARCHAR(16) DEFAULT 'markdown'",
        "anchor_event_id": "VARCHAR(36)",
        "anchor_event_title": "VARCHAR(255)",
        "structured_sources": "JSON",
        "web_sources": "JSON",
    }
    for column_name, column_type in required_column_sql.items():
        if column_name in existing_columns:
            continue
        sync_connection.execute(
            text(
                f"ALTER TABLE analysis_reports ADD COLUMN {column_name} {column_type}"
            )
        )

    if "analysis_generation_sessions" not in set(inspector.get_table_names()):
        return

    session_columns = {
        item["name"] for item in inspector.get_columns("analysis_generation_sessions")
    }
    if "anchor_event_id" not in session_columns:
        sync_connection.execute(
            text(
                "ALTER TABLE analysis_generation_sessions ADD COLUMN anchor_event_id VARCHAR(36)"
            )
        )


def _ensure_stock_candidate_evidence_cache_columns(sync_connection: Connection) -> None:
    inspector = inspect(sync_connection)
    if "stock_candidate_evidence_cache" not in set(inspector.get_table_names()):
        return

    existing_columns = {
        item["name"] for item in inspector.get_columns("stock_candidate_evidence_cache")
    }
    required_column_sql: dict[str, str] = {
        "evidence_kind": "VARCHAR(32)",
        "ts_code": "VARCHAR(12)",
        "symbol": "VARCHAR(16)",
        "name": "VARCHAR(128)",
        "title": "VARCHAR(255)",
        "summary": "TEXT",
        "published_at": "TIMESTAMP",
        "url": "VARCHAR(1024)",
        "source": "VARCHAR(64) DEFAULT 'akshare'",
        "fetched_at": "TIMESTAMP",
    }
    for column_name, column_type in required_column_sql.items():
        if column_name in existing_columns:
            continue
        sync_connection.execute(
            text(
                "ALTER TABLE stock_candidate_evidence_cache "
                f"ADD COLUMN {column_name} {column_type}"
            )
        )


async def ensure_initial_admin_user(
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> None:
    if not settings.init_admin_enabled:
        return

    admin_username = settings.init_admin_username.strip()
    admin_email = settings.init_admin_email.strip().lower()
    admin_password = settings.init_admin_password.strip()

    # 鉴权边界：只有在三个种子参数都提供时才创建首个管理员，避免误创建弱配置账户。
    if not (admin_username and admin_email and admin_password):
        return

    session_maker = session_factory or SessionLocal
    async with session_maker() as session:
        existing_admin_statement = (
            select(User.id).where(User.user_level == USER_LEVEL_ADMIN).limit(1)
        )
        existing_admin = await session.execute(existing_admin_statement)
        if existing_admin.scalar_one_or_none() is not None:
            return

        conflict_statement = (
            select(User.id)
            .where(or_(User.username == admin_username, User.email == admin_email))
            .limit(1)
        )
        conflict = await session.execute(conflict_statement)
        if conflict.scalar_one_or_none() is not None:
            # 关键分支：种子管理员与现有账号冲突时直接跳过，防止覆盖或破坏已有账户。
            logger.warning(
                "event=auth.bootstrap_admin.skipped reason=account_conflict username=%s email=%s",
                admin_username,
                admin_email,
            )
            return

        admin_user = User(
            username=admin_username,
            email=admin_email,
            password_hash=hash_password(admin_password),
            user_level=USER_LEVEL_ADMIN,
        )
        session.add(admin_user)
        await session.commit()
        await session.refresh(admin_user)

    logger.info(
        "event=auth.bootstrap_admin.created user_id=%s username=%s",
        admin_user.id,
        admin_user.username,
    )


async def ensure_database_schema(
    *,
    settings: Settings | None = None,
    target_engine: AsyncEngine | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> None:
    await ensure_database_schema_with_runtime(
        settings=settings or get_settings(),
        target_engine=target_engine or engine,
        session_factory=session_factory or SessionLocal,
    )


async def upgrade_database_schema(
    *,
    settings: Settings,
    target_engine: AsyncEngine,
) -> None:
    _ = settings, target_engine
    await run_database_migrations()


async def validate_database_schema(
    *,
    settings: Settings,
    target_engine: AsyncEngine,
) -> None:
    _ = settings
    await validate_database_schema_revision(target_engine=target_engine)


async def ensure_database_schema_with_runtime(
    *,
    settings: Settings,
    target_engine: AsyncEngine,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> None:
    if settings.should_auto_apply_schema:
        if settings.db_auto_create_database:
            # 开发模式允许先补数据库与 schema，再执行迁移，降低本地首次启动门槛。
            await ensure_database_exists(settings)
        await ensure_postgres_schema_exists(settings)
        await upgrade_database_schema(settings=settings, target_engine=target_engine)
    else:
        # 非开发环境只校验迁移版本，避免服务启动时隐式改表。
        await validate_database_schema(settings=settings, target_engine=target_engine)

    if settings.init_admin_enabled:
        # 显式开启种子管理员时才执行初始化，避免校验模式下仍触发账户侧副作用。
        await ensure_initial_admin_user(settings, session_factory=session_factory)
    logger.info(
        "event=db.schema.ensure.success tables=%s",
        ",".join(sorted(Base.metadata.tables.keys())),
    )
