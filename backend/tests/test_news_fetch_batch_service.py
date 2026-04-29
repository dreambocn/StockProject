import asyncio
from datetime import UTC, datetime

from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import async_sessionmaker

from conftest import build_sqlite_test_context, init_sqlite_schema

from app.db.base import Base
from app.db.init_db import ensure_schema_for_engine
from app.services.news_fetch_batch_service import (
    NEWS_FETCH_SCOPE_HOT,
    NEWS_FETCH_SCOPE_STOCK,
    NEWS_FETCH_STATUS_FAILED,
    NEWS_FETCH_STATUS_PARTIAL,
    NEWS_FETCH_STATUS_SUCCESS,
    create_news_fetch_batch,
    finalize_news_fetch_batch,
    load_latest_news_fetch_batch,
)


def _setup_async_session(tmp_path):
    engine, session_maker = build_sqlite_test_context(tmp_path, "news-fetch-batch.db")
    init_sqlite_schema(engine)
    return engine, session_maker


def test_news_fetch_batch_lifecycle_records_metrics(tmp_path) -> None:
    engine, session_maker = _setup_async_session(tmp_path)

    async def run_test() -> None:
        async with session_maker() as session:
            batch = await create_news_fetch_batch(
                session,
                scope=NEWS_FETCH_SCOPE_HOT,
                cache_variant="global",
                trigger_source="api.news.hot",
                started_at=datetime(2026, 3, 25, 10, 0, tzinfo=UTC),
                fetched_at=datetime(2026, 3, 25, 10, 1, tzinfo=UTC),
            )
            await finalize_news_fetch_batch(
                session,
                batch=batch,
                status=NEWS_FETCH_STATUS_PARTIAL,
                finished_at=datetime(2026, 3, 25, 10, 0, 2, tzinfo=UTC),
                row_count_raw=12,
                row_count_mapped=8,
                row_count_persisted=8,
                provider_stats=[
                    {
                        "provider": "akshare",
                        "status": "success",
                        "latency_ms": 120,
                        "raw_count": 12,
                        "mapped_count": 8,
                        "persisted_count": 8,
                    }
                ],
                degrade_reasons=["hot.tushare_failed"],
                error_type="RuntimeError",
                error_message="上游服务短暂超时",
            )
            await session.commit()
            await session.refresh(batch)

            assert batch.status == NEWS_FETCH_STATUS_PARTIAL
            assert batch.duration_ms == 2000
            assert batch.row_count_raw == 12
            assert batch.row_count_mapped == 8
            assert batch.row_count_persisted == 8
            assert batch.provider_stats_json and batch.provider_stats_json[0]["provider"] == "akshare"
            assert batch.degrade_reasons_json == ["hot.tushare_failed"]
            assert batch.error_type == "RuntimeError"
            assert batch.error_message == "上游服务短暂超时"

    asyncio.run(run_test())


def test_load_latest_news_fetch_batch_prefers_completed_statuses(tmp_path) -> None:
    engine, session_maker = _setup_async_session(tmp_path)

    async def run_test() -> None:
        async with session_maker() as session:
            batch_success = await create_news_fetch_batch(
                session,
                scope=NEWS_FETCH_SCOPE_STOCK,
                cache_variant="with_announcements",
                ts_code="600029.SH",
                trigger_source="api.stocks.news",
                started_at=datetime(2026, 3, 25, 8, 0, tzinfo=UTC),
                fetched_at=datetime(2026, 3, 25, 8, 1, tzinfo=UTC),
            )
            await finalize_news_fetch_batch(
                session,
                batch=batch_success,
                status=NEWS_FETCH_STATUS_SUCCESS,
                finished_at=datetime(2026, 3, 25, 8, 0, 2, tzinfo=UTC),
            )

            batch_failed = await create_news_fetch_batch(
                session,
                scope=NEWS_FETCH_SCOPE_STOCK,
                cache_variant="with_announcements",
                ts_code="600029.SH",
                trigger_source="api.stocks.news",
                started_at=datetime(2026, 3, 25, 9, 0, tzinfo=UTC),
                fetched_at=datetime(2026, 3, 25, 9, 1, tzinfo=UTC),
            )
            await finalize_news_fetch_batch(
                session,
                batch=batch_failed,
                status=NEWS_FETCH_STATUS_FAILED,
                finished_at=datetime(2026, 3, 25, 9, 0, 2, tzinfo=UTC),
            )

            batch_partial = await create_news_fetch_batch(
                session,
                scope=NEWS_FETCH_SCOPE_STOCK,
                cache_variant="with_announcements",
                ts_code="600029.SH",
                trigger_source="worker.watchlist.hourly",
                started_at=datetime(2026, 3, 25, 10, 0, tzinfo=UTC),
                fetched_at=datetime(2026, 3, 25, 10, 1, tzinfo=UTC),
            )
            await finalize_news_fetch_batch(
                session,
                batch=batch_partial,
                status=NEWS_FETCH_STATUS_PARTIAL,
                finished_at=datetime(2026, 3, 25, 10, 0, 2, tzinfo=UTC),
            )
            await session.commit()

            latest_completed = await load_latest_news_fetch_batch(
                session,
                scope=NEWS_FETCH_SCOPE_STOCK,
                cache_variant="with_announcements",
                ts_code="600029.SH",
            )
            latest_failed = await load_latest_news_fetch_batch(
                session,
                scope=NEWS_FETCH_SCOPE_STOCK,
                cache_variant="with_announcements",
                ts_code="600029.SH",
                statuses=(NEWS_FETCH_STATUS_FAILED,),
            )

            assert latest_completed is not None
            assert latest_completed.id == batch_partial.id
            assert latest_failed is not None
            assert latest_failed.id == batch_failed.id

    asyncio.run(run_test())


def test_ensure_schema_adds_news_fetch_batch_structures(tmp_path) -> None:
    db_path = tmp_path / "news-fetch-schema.db"
    db_url = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    engine, _ = build_sqlite_test_context(tmp_path, "news-fetch-schema.db")

    async def run_test() -> None:
        await ensure_schema_for_engine(engine)
        async with engine.begin() as connection:
            tables = await connection.run_sync(
                lambda sync_conn: set(inspect(sync_conn).get_table_names())
            )
            news_columns = await connection.run_sync(
                lambda sync_conn: {
                    item["name"] for item in inspect(sync_conn).get_columns("news_events")
                }
            )
            batch_columns = await connection.run_sync(
                lambda sync_conn: {
                    item["name"]
                    for item in inspect(sync_conn).get_columns("news_fetch_batches")
                }
            )
            batch_indexes = await connection.run_sync(
                lambda sync_conn: {
                    item["name"]
                    for item in inspect(sync_conn).get_indexes("news_fetch_batches")
                }
            )

        assert "news_fetch_batches" in tables
        assert "batch_id" in news_columns
        assert "provider_stats_json" in batch_columns
        assert "degrade_reasons_json" in batch_columns
        assert "ix_news_fetch_batches_scope_cache_variant_fetched_at" in batch_indexes
        assert "ix_news_fetch_batches_scope_ts_code_cache_variant_fetched_at" in batch_indexes
        assert "ix_news_fetch_batches_status_finished_at" in batch_indexes
        assert "ix_news_fetch_batches_trigger_source_finished_at" in batch_indexes

    asyncio.run(run_test())
