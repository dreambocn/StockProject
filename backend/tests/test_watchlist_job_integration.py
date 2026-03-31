import asyncio
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models.stock_instrument import StockInstrument
from app.models.system_job_run import SystemJobRun
from app.models.user import User
from app.models.user_watchlist_item import UserWatchlistItem
from app.services.watchlist_worker_service import (
    run_daily_watchlist_analysis,
    run_hourly_watchlist_sync,
)


def test_watchlist_workers_create_system_jobs(tmp_path) -> None:
    db_file = tmp_path / "watchlist-job.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_file.as_posix()}")
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    async def run_test() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        async with session_maker() as session:
            session.add_all(
                [
                    User(
                        id="user-1",
                        username="watcher",
                        email="watcher@example.com",
                        password_hash="hashed",
                    ),
                    StockInstrument(
                        ts_code="600519.SH",
                        symbol="600519",
                        name="贵州茅台",
                        fullname="贵州茅台酒股份有限公司",
                        list_status="L",
                    ),
                    UserWatchlistItem(user_id="user-1", ts_code="600519.SH"),
                ]
            )
            await session.commit()

            async def fake_sync_stock_watch_context(*, session, ts_code: str, now: datetime):
                _ = session, ts_code, now

            async def fake_start_analysis_session(
                session,
                ts_code: str,
                *,
                topic: str | None,
                force_refresh: bool,
                use_web_search: bool,
                trigger_source: str,
                execute_inline: bool,
            ):
                _ = session, topic, force_refresh, use_web_search, trigger_source, execute_inline
                return {
                    "session_id": "analysis-session-1",
                    "report_id": None,
                    "status": "queued",
                    "reused": False,
                    "cached": False,
                }

            await run_hourly_watchlist_sync(
                session,
                now=datetime(2026, 3, 31, 9, 5, tzinfo=UTC),
                sync_stock_watch_context=fake_sync_stock_watch_context,
            )
            await run_daily_watchlist_analysis(
                session,
                now=datetime(2026, 3, 31, 18, 10, tzinfo=UTC),
                start_analysis_session_fn=fake_start_analysis_session,
                execute_inline=True,
            )

            jobs = (
                await session.execute(
                    select(SystemJobRun).order_by(SystemJobRun.job_type.asc())
                )
            ).scalars().all()

            assert [job.job_type for job in jobs] == [
                "watchlist_daily_analysis",
                "watchlist_hourly_sync",
            ]
            assert all(job.status == "success" for job in jobs)

        await engine.dispose()

    asyncio.run(run_test())
