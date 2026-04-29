import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from conftest import build_sqlite_test_context, init_sqlite_schema

from app.db.base import Base
from app.models.system_job_run import SystemJobRun
from app.services.news_fetch_batch_service import (
    NEWS_FETCH_STATUS_SUCCESS,
    create_news_fetch_batch,
    finalize_news_fetch_batch,
)


def test_news_fetch_batch_creates_and_finishes_system_job(tmp_path) -> None:
    db_file = tmp_path / "news-fetch-job.db"
    engine, session_maker = build_sqlite_test_context(tmp_path, "news-fetch-job.db")

    async def run_test() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        async with session_maker() as session:
            batch = await create_news_fetch_batch(
                session,
                scope="hot",
                cache_variant="global",
                trigger_source="api.news.hot",
            )
            await finalize_news_fetch_batch(
                session,
                batch=batch,
                status=NEWS_FETCH_STATUS_SUCCESS,
                row_count_raw=3,
                row_count_mapped=2,
                row_count_persisted=2,
            )
            await session.commit()

        async with session_maker() as session:
            job_row = (
                await session.execute(select(SystemJobRun).limit(1))
            ).scalar_one()
            assert job_row.job_type == "news_fetch"
            assert job_row.status == "success"
            assert job_row.linked_entity_type == "news_fetch_batch"
            assert job_row.metrics_json["row_count_persisted"] == 2


    asyncio.run(run_test())
