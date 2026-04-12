import asyncio
from pathlib import Path

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.db.migrations import build_alembic_config, run_database_migrations, validate_database_schema


def test_alembic_upgrade_head_creates_core_tables(tmp_path: Path) -> None:
    db_file = tmp_path / "alembic-smoke.db"
    database_url = f"sqlite+aiosqlite:///{db_file.as_posix()}"

    async def run_test() -> None:
        config = build_alembic_config(database_url=database_url)
        await run_database_migrations(config=config)
        engine = create_async_engine(database_url)
        try:
            async with engine.begin() as connection:
                tables = await connection.run_sync(
                    lambda sync_conn: set(inspect(sync_conn).get_table_names())
                )
                version_num = await connection.execute(text("SELECT version_num FROM alembic_version"))
                current_version = version_num.scalar_one()

            assert "users" in tables
            assert "analysis_reports" in tables
            assert "analysis_generation_sessions" in tables
            assert "news_events" in tables
            assert current_version

            await validate_database_schema(target_engine=engine, config=config)
        finally:
            await engine.dispose()

    asyncio.run(run_test())


def test_alembic_upgrade_head_stamps_legacy_baseline_then_applies_followup_revisions(
    tmp_path: Path,
) -> None:
    db_file = tmp_path / "alembic-legacy-baseline.db"
    database_url = f"sqlite+aiosqlite:///{db_file.as_posix()}"

    async def run_test() -> None:
        config = build_alembic_config(database_url=database_url)
        await run_database_migrations(config=config, revision="20260331_0001")
        engine = create_async_engine(database_url)
        try:
            async with engine.begin() as connection:
                await connection.execute(text("DROP TABLE alembic_version"))

            await run_database_migrations(config=config)

            async with engine.begin() as connection:
                tables = await connection.run_sync(
                    lambda sync_conn: set(inspect(sync_conn).get_table_names())
                )
                report_columns = await connection.run_sync(
                    lambda sync_conn: {
                        column["name"]
                        for column in inspect(sync_conn).get_columns("analysis_reports")
                    }
                )
                version_num = await connection.execute(
                    text("SELECT version_num FROM alembic_version")
                )
                current_version = version_num.scalar_one()

            assert "system_job_runs" in tables
            assert "market_themes" in tables
            assert "policy_documents" in tables
            assert "analysis_agent_runs" in tables
            assert "prompt_version" in report_columns
            assert "evidence_event_count" in report_columns
            assert "evidence_events" in report_columns
            assert "analysis_mode" in report_columns
            assert current_version == "20260412_0008"
        finally:
            await engine.dispose()

    asyncio.run(run_test())
