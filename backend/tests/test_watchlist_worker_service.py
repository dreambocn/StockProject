import asyncio
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models.analysis_report import AnalysisReport
from app.models.stock_instrument import StockInstrument
from app.models.user import User
from app.models.user_watchlist_item import UserWatchlistItem
from app.services.watchlist_worker_service import (
    run_daily_watchlist_analysis,
    run_hourly_watchlist_sync,
    sync_stock_watch_context,
)


def _setup_async_session(tmp_path: Path):
    db_path = tmp_path / "watchlist-worker.db"
    db_url = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    engine = create_async_engine(db_url)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    async def _create_tables() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(_create_tables())
    return engine, session_maker


async def _seed_watchlist_users(session) -> None:
    session.add_all(
        [
            User(
                id="user-1",
                username="watcher-1",
                email="watcher-1@example.com",
                password_hash="hashed",
            ),
            User(
                id="user-2",
                username="watcher-2",
                email="watcher-2@example.com",
                password_hash="hashed",
            ),
            User(
                id="user-3",
                username="watcher-3",
                email="watcher-3@example.com",
                password_hash="hashed",
            ),
            StockInstrument(
                ts_code="600519.SH",
                symbol="600519",
                name="贵州茅台",
                fullname="贵州茅台酒股份有限公司",
                list_status="L",
            ),
            StockInstrument(
                ts_code="000001.SZ",
                symbol="000001",
                name="平安银行",
                fullname="平安银行股份有限公司",
                list_status="L",
            ),
        ]
    )
    await session.commit()


def test_run_hourly_watchlist_sync_deduplicates_targets(tmp_path: Path) -> None:
    engine, session_maker = _setup_async_session(tmp_path)

    async def run_test() -> None:
        async with session_maker() as session:
            await _seed_watchlist_users(session)
            session.add_all(
                [
                    UserWatchlistItem(user_id="user-1", ts_code="600519.SH"),
                    UserWatchlistItem(user_id="user-2", ts_code="600519.SH"),
                    UserWatchlistItem(
                        user_id="user-3",
                        ts_code="000001.SZ",
                        hourly_sync_enabled=False,
                    ),
                ]
            )
            await session.commit()

            visited: list[str] = []

            async def fake_sync_stock_watch_context(*, session, ts_code: str, now: datetime):
                _ = session, now
                visited.append(ts_code)

            now = datetime(2026, 3, 23, 9, 5, tzinfo=UTC)
            result = await run_hourly_watchlist_sync(
                session,
                now=now,
                sync_stock_watch_context=fake_sync_stock_watch_context,
            )

            assert result["processed"] == 1
            assert result["skipped"] == 0
            assert visited == ["600519.SH"]

            rows = (
                await session.execute(
                    select(UserWatchlistItem).order_by(UserWatchlistItem.user_id.asc())
                )
            ).scalars().all()
            assert rows[0].last_hourly_sync_at == now.replace(tzinfo=None)
            assert rows[1].last_hourly_sync_at == now.replace(tzinfo=None)
            assert rows[2].last_hourly_sync_at is None

    try:
        asyncio.run(run_test())
    finally:
        asyncio.run(engine.dispose())


def test_run_daily_watchlist_analysis_deduplicates_and_skips_existing_report(
    tmp_path: Path,
) -> None:
    engine, session_maker = _setup_async_session(tmp_path)

    async def run_test() -> None:
        async with session_maker() as session:
            await _seed_watchlist_users(session)
            session.add_all(
                [
                    UserWatchlistItem(
                        user_id="user-1",
                        ts_code="600519.SH",
                        web_search_enabled=False,
                    ),
                    UserWatchlistItem(
                        user_id="user-2",
                        ts_code="600519.SH",
                        web_search_enabled=True,
                    ),
                    UserWatchlistItem(
                        user_id="user-3",
                        ts_code="000001.SZ",
                        web_search_enabled=False,
                    ),
                ]
            )
            session.add(
                AnalysisReport(
                    ts_code="000001.SZ",
                    status="ready",
                    summary="# 已有日报",
                    risk_points=[],
                    factor_breakdown=[],
                    trigger_source="watchlist_daily",
                    used_web_search=False,
                    web_search_status="disabled",
                    content_format="markdown",
                    generated_at=datetime(2026, 3, 23, 18, 0, tzinfo=UTC),
                    started_at=datetime(2026, 3, 23, 17, 59, tzinfo=UTC),
                    completed_at=datetime(2026, 3, 23, 18, 0, tzinfo=UTC),
                )
            )
            await session.commit()

            called: list[tuple[str, bool, str, bool]] = []

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
                _ = session, topic, force_refresh
                called.append((ts_code, use_web_search, trigger_source, execute_inline))
                return {
                    "session_id": "session-1",
                    "report_id": "report-1",
                    "status": "completed",
                    "reused": False,
                    "cached": False,
                }

            now = datetime(2026, 3, 23, 18, 10, tzinfo=UTC)
            result = await run_daily_watchlist_analysis(
                session,
                now=now,
                start_analysis_session_fn=fake_start_analysis_session,
                execute_inline=True,
            )

            assert result["processed"] == 1
            assert result["skipped"] == 1
            assert called == [("600519.SH", True, "watchlist_daily", True)]

            rows = (
                await session.execute(
                    select(UserWatchlistItem).order_by(UserWatchlistItem.user_id.asc())
                )
            ).scalars().all()
            assert rows[0].last_daily_analysis_at == now.replace(tzinfo=None)
            assert rows[1].last_daily_analysis_at == now.replace(tzinfo=None)
            assert rows[2].last_daily_analysis_at == now.replace(tzinfo=None)

    try:
        asyncio.run(run_test())
    finally:
        asyncio.run(engine.dispose())


def test_sync_stock_watch_context_logs_warning_when_announcement_fetch_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    engine, session_maker = _setup_async_session(tmp_path)
    warning_calls: list[tuple[str, tuple[object, ...]]] = []

    async def fake_fetch_stock_news(_symbol: str) -> list[dict[str, object]]:
        return []

    async def fake_fetch_stock_announcements(*, symbol: str) -> list[dict[str, object]]:
        _ = symbol
        raise RuntimeError("announcement upstream down")

    def fake_warning(message: str, *args: object, **kwargs: object) -> None:
        _ = kwargs
        warning_calls.append((message, args))

    monkeypatch.setattr(
        "app.services.watchlist_worker_service.fetch_stock_news",
        fake_fetch_stock_news,
    )
    monkeypatch.setattr(
        "app.services.watchlist_worker_service.fetch_stock_announcements",
        fake_fetch_stock_announcements,
    )
    monkeypatch.setattr(
        "app.services.watchlist_worker_service.logger.warning",
        fake_warning,
    )

    async def run_test() -> None:
        async with session_maker() as session:
            await _seed_watchlist_users(session)
            now = datetime(2026, 3, 23, 9, 5, tzinfo=UTC)
            await sync_stock_watch_context(session=session, ts_code="600519.SH", now=now)

    try:
        asyncio.run(run_test())
    finally:
        asyncio.run(engine.dispose())

    assert any(
        call_args[:3] == ("600519.SH", "announcement", "RuntimeError")
        for _message, call_args in warning_calls
    )


def test_sync_stock_watch_context_logs_warning_when_news_fetch_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    engine, session_maker = _setup_async_session(tmp_path)
    warning_calls: list[tuple[str, tuple[object, ...]]] = []

    async def fake_fetch_stock_news(_symbol: str) -> list[dict[str, object]]:
        raise RuntimeError("news upstream down")

    async def fake_fetch_stock_announcements(*, symbol: str) -> list[dict[str, object]]:
        _ = symbol
        return []

    def fake_warning(message: str, *args: object, **kwargs: object) -> None:
        _ = kwargs
        warning_calls.append((message, args))

    monkeypatch.setattr(
        "app.services.watchlist_worker_service.fetch_stock_news",
        fake_fetch_stock_news,
    )
    monkeypatch.setattr(
        "app.services.watchlist_worker_service.fetch_stock_announcements",
        fake_fetch_stock_announcements,
    )
    monkeypatch.setattr(
        "app.services.watchlist_worker_service.logger.warning",
        fake_warning,
    )

    async def run_test() -> None:
        async with session_maker() as session:
            await _seed_watchlist_users(session)
            now = datetime(2026, 3, 23, 9, 5, tzinfo=UTC)
            await sync_stock_watch_context(session=session, ts_code="600519.SH", now=now)

    try:
        asyncio.run(run_test())
    finally:
        asyncio.run(engine.dispose())

    assert any(
        call_args[:3] == ("600519.SH", "news", "RuntimeError")
        for _message, call_args in warning_calls
    )


def test_run_hourly_watchlist_sync_logs_warning_for_item_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    engine, session_maker = _setup_async_session(tmp_path)
    warning_calls: list[tuple[str, tuple[object, ...]]] = []

    def fake_warning(message: str, *args: object, **kwargs: object) -> None:
        _ = kwargs
        warning_calls.append((message, args))

    monkeypatch.setattr(
        "app.services.watchlist_worker_service.logger.warning",
        fake_warning,
    )

    async def run_test() -> None:
        async with session_maker() as session:
            await _seed_watchlist_users(session)
            session.add(UserWatchlistItem(user_id="user-1", ts_code="600519.SH"))
            await session.commit()

            async def fake_sync_stock_watch_context(*, session, ts_code: str, now: datetime):
                _ = session, ts_code, now
                raise RuntimeError("sync failed")

            now = datetime(2026, 3, 23, 9, 5, tzinfo=UTC)
            result = await run_hourly_watchlist_sync(
                session,
                now=now,
                sync_stock_watch_context=fake_sync_stock_watch_context,
            )

            assert result["processed"] == 0
            assert result["skipped"] == 1

    try:
        asyncio.run(run_test())
    finally:
        asyncio.run(engine.dispose())

    assert any(
        call_args[:3] == ("600519.SH", "hourly_sync", "RuntimeError")
        for _message, call_args in warning_calls
    )


def test_run_daily_watchlist_analysis_logs_warning_for_item_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    engine, session_maker = _setup_async_session(tmp_path)
    warning_calls: list[tuple[str, tuple[object, ...]]] = []

    def fake_warning(message: str, *args: object, **kwargs: object) -> None:
        _ = kwargs
        warning_calls.append((message, args))

    monkeypatch.setattr(
        "app.services.watchlist_worker_service.logger.warning",
        fake_warning,
    )

    async def run_test() -> None:
        async with session_maker() as session:
            await _seed_watchlist_users(session)
            session.add(UserWatchlistItem(user_id="user-1", ts_code="600519.SH"))
            await session.commit()

            async def fake_start_analysis_session(
                _session,
                _ts_code: str,
                *,
                topic: str | None,
                force_refresh: bool,
                use_web_search: bool,
                trigger_source: str,
                execute_inline: bool,
            ):
                _ = (
                    topic,
                    force_refresh,
                    use_web_search,
                    trigger_source,
                    execute_inline,
                )
                raise RuntimeError("analysis failed")

            now = datetime(2026, 3, 23, 18, 10, tzinfo=UTC)
            result = await run_daily_watchlist_analysis(
                session,
                now=now,
                start_analysis_session_fn=fake_start_analysis_session,
                execute_inline=True,
            )

            assert result["processed"] == 0
            assert result["skipped"] == 1

    try:
        asyncio.run(run_test())
    finally:
        asyncio.run(engine.dispose())

    assert any(
        call_args[:3] == ("600519.SH", "daily_analysis", "RuntimeError")
        for _message, call_args in warning_calls
    )
