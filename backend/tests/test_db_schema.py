import asyncio

from sqlalchemy import select
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.settings import Settings
from app.db.init_db import (
    ensure_database_exists,
    ensure_initial_admin_user,
    ensure_postgres_schema_exists,
    ensure_schema_for_engine,
)
from app.models.user import User


def test_ensure_schema_creates_required_tables(tmp_path) -> None:
    db_file = tmp_path / "schema-check.db"
    db_url = f"sqlite+aiosqlite:///{db_file.as_posix()}"
    engine = create_async_engine(db_url)

    async def run_test() -> None:
        async with engine.begin() as connection:
            before_tables = await connection.run_sync(
                lambda sync_conn: inspect(sync_conn).get_table_names()
            )

        assert "users" not in before_tables

        await ensure_schema_for_engine(engine)

        async with engine.begin() as connection:
            after_tables = await connection.run_sync(
                lambda sync_conn: inspect(sync_conn).get_table_names()
            )
            news_columns = await connection.run_sync(
                lambda sync_conn: {
                    item["name"]
                    for item in inspect(sync_conn).get_columns("news_events")
                }
            )

        assert "users" in after_tables
        assert "news_events" in after_tables
        assert "analysis_event_links" in after_tables
        assert "analysis_reports" in after_tables
        assert "analysis_generation_sessions" in after_tables
        assert "analysis_evaluation_datasets" in after_tables
        assert "analysis_evaluation_cases" in after_tables
        assert "analysis_evaluation_runs" in after_tables
        assert "analysis_evaluation_case_results" in after_tables
        assert "web_source_metadata_cache" in after_tables
        assert "user_watchlist_items" in after_tables
        assert "stock_watch_snapshots" in after_tables
        assert "event_type" in news_columns
        assert "sentiment_label" in news_columns
        assert "sentiment_score" in news_columns
        assert "event_tags" in news_columns
        assert "analysis_status" in news_columns
        assert "provider" in news_columns
        assert "external_id" in news_columns
        assert "cluster_key" in news_columns
        assert "source_priority" in news_columns
        assert "evidence_kind" in news_columns
        async with engine.begin() as connection:
            report_columns = await connection.run_sync(
                lambda sync_conn: {
                    item["name"]
                    for item in inspect(sync_conn).get_columns("analysis_reports")
                }
            )

        assert "trigger_source" in report_columns
        assert "used_web_search" in report_columns
        assert "web_search_status" in report_columns
        assert "session_id" in report_columns
        assert "started_at" in report_columns
        assert "completed_at" in report_columns
        assert "content_format" in report_columns
        assert "web_sources" in report_columns
        assert "anchor_event_id" in report_columns
        assert "anchor_event_title" in report_columns
        assert "structured_sources" in report_columns
        async with engine.begin() as connection:
            session_columns = await connection.run_sync(
                lambda sync_conn: {
                    item["name"]
                    for item in inspect(sync_conn).get_columns("analysis_generation_sessions")
                }
            )

        assert "anchor_event_id" in session_columns

        async with engine.begin() as connection:
            evaluation_run_columns = await connection.run_sync(
                lambda sync_conn: {
                    item["name"]
                    for item in inspect(sync_conn).get_columns(
                        "analysis_evaluation_runs"
                    )
                }
            )
            evaluation_result_columns = await connection.run_sync(
                lambda sync_conn: {
                    item["name"]
                    for item in inspect(sync_conn).get_columns(
                        "analysis_evaluation_case_results"
                    )
                }
            )

        assert "run_key" in evaluation_run_columns
        assert "variant_key" in evaluation_run_columns
        assert "prompt_profile_key" in evaluation_run_columns
        assert "event_top1_hit_rate" in evaluation_run_columns
        assert "factor_top1_accuracy" in evaluation_run_columns
        assert "citation_metadata_completeness_rate" in evaluation_run_columns
        assert "avg_latency_ms" in evaluation_run_columns

        assert "event_top1_hit" in evaluation_result_columns
        assert "factor_top1_hit" in evaluation_result_columns
        assert "citation_metadata_completeness_rate" in evaluation_result_columns
        assert "latency_ms" in evaluation_result_columns
        assert "top_event_title" in evaluation_result_columns
        assert "top_factor_key" in evaluation_result_columns
        assert "web_source_count" in evaluation_result_columns
        assert "result_snapshot" in evaluation_result_columns

        await engine.dispose()

    asyncio.run(run_test())


def test_ensure_database_exists_creates_missing_database() -> None:
    class FakeConnection:
        def __init__(self) -> None:
            self.executed: list[str] = []
            self.closed = False

        async def fetch(self, _: str):
            return [{"datname": "postgres"}, {"datname": "DreamBoDB"}]

        async def execute(self, sql: str):
            self.executed.append(sql)

        async def close(self):
            self.closed = True

    fake_connection = FakeConnection()

    async def fake_connector(**kwargs):
        assert kwargs["database"] == "postgres"
        return fake_connection

    settings = Settings(
        postgres_jdbc_url="jdbc:postgresql://127.0.0.1:5432/stockdb",
        postgres_user="postgres",
        postgres_password="postgres",
        redis_jdbc_url="jdbc:redis://127.0.0.1:6379/0",
    )

    asyncio.run(ensure_database_exists(settings, connector=fake_connector))

    assert fake_connection.executed == ['create database "stockdb"']
    assert fake_connection.closed is True


def test_ensure_postgres_schema_exists_creates_missing_schema() -> None:
    class FakeConnection:
        def __init__(self) -> None:
            self.executed: list[str] = []
            self.closed = False

        async def fetchval(self, _: str, __: str):
            return None

        async def execute(self, sql: str):
            self.executed.append(sql)

        async def close(self):
            self.closed = True

    fake_connection = FakeConnection()

    async def fake_connector(**kwargs):
        assert kwargs["database"] == "DreamBoDB"
        return fake_connection

    settings = Settings(
        postgres_jdbc_url="jdbc:postgresql://127.0.0.1:5432/DreamBoDB.stockdb",
        postgres_user="postgres",
        postgres_password="postgres",
        redis_jdbc_url="jdbc:redis://127.0.0.1:6379/0",
    )

    asyncio.run(ensure_postgres_schema_exists(settings, connector=fake_connector))

    assert fake_connection.executed == ['create schema "stockdb"']
    assert fake_connection.closed is True


def test_ensure_initial_admin_user_creates_seed_admin(tmp_path) -> None:
    db_file = tmp_path / "seed-admin.db"
    db_url = f"sqlite+aiosqlite:///{db_file.as_posix()}"
    engine = create_async_engine(db_url)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    settings = Settings(
        postgres_jdbc_url="jdbc:postgresql://127.0.0.1:5432/DreamBoDB.stockdb",
        postgres_user="postgres",
        postgres_password="postgres",
        redis_jdbc_url="jdbc:redis://127.0.0.1:6379/0",
        init_admin_username="admin-root",
        init_admin_email="admin-root@example.com",
        init_admin_password="StrongP@ss1",
    )

    async def run_test() -> None:
        await ensure_schema_for_engine(engine)
        await ensure_initial_admin_user(settings, session_factory=session_maker)

        async with session_maker() as session:
            result = await session.execute(
                select(User).where(User.username == "admin-root")
            )
            admin = result.scalar_one_or_none()

        assert admin is not None
        assert admin.email == "admin-root@example.com"
        assert admin.user_level == "admin"

        await engine.dispose()

    asyncio.run(run_test())
