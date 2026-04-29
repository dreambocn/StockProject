import asyncio

from sqlalchemy import inspect

from conftest import build_sqlite_test_context, init_sqlite_schema

from app.db.base import Base


def test_system_job_runs_table_and_links_exist(tmp_path) -> None:
    db_file = tmp_path / "system-job-model.db"
    engine, _ = build_sqlite_test_context(tmp_path, "system-job-model.db")

    async def run_test() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
            table_names = await connection.run_sync(
                lambda sync_conn: set(inspect(sync_conn).get_table_names())
            )
            job_columns = await connection.run_sync(
                lambda sync_conn: {
                    item["name"] for item in inspect(sync_conn).get_columns("system_job_runs")
                }
            )
            analysis_session_columns = await connection.run_sync(
                lambda sync_conn: {
                    item["name"]
                    for item in inspect(sync_conn).get_columns("analysis_generation_sessions")
                }
            )
            batch_columns = await connection.run_sync(
                lambda sync_conn: {
                    item["name"] for item in inspect(sync_conn).get_columns("news_fetch_batches")
                }
            )

        assert "system_job_runs" in table_names
        assert "job_type" in job_columns
        assert "status" in job_columns
        assert "resource_key" in job_columns
        assert "payload_json" in job_columns
        assert "metrics_json" in job_columns
        assert "heartbeat_at" in job_columns
        assert "system_job_id" in analysis_session_columns
        assert "system_job_id" in batch_columns


    asyncio.run(run_test())
