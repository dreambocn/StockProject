import asyncio
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models.news_event import NewsEvent
from app.services.analysis_repository import load_recent_news_events


def _setup_async_session(tmp_path: Path):
    db_path = tmp_path / "analysis-repository.db"
    db_url = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    engine = create_async_engine(db_url)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    async def _create_tables() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(_create_tables())
    return engine, session_maker


def test_load_recent_news_events_dedupes_archived_batches(tmp_path: Path) -> None:
    engine, session_maker = _setup_async_session(tmp_path)

    async def run_test() -> None:
        async with session_maker() as session:
            session.add_all(
                [
                    NewsEvent(
                        id="stock-archive-v1",
                        scope="stock",
                        cache_variant="with_announcements",
                        ts_code="600519.SH",
                        symbol="600519",
                        title="贵州茅台业绩增长超预期",
                        summary="旧批次",
                        published_at=datetime(2026, 3, 20, 9, 0, tzinfo=UTC),
                        url="https://example.com/stock-archive",
                        publisher="测试源",
                        source="eastmoney_stock",
                        fetched_at=datetime(2026, 3, 20, 9, 5, tzinfo=UTC),
                    ),
                    NewsEvent(
                        id="stock-archive-v2",
                        scope="stock",
                        cache_variant="with_announcements",
                        ts_code="600519.SH",
                        symbol="600519",
                        title="贵州茅台业绩增长超预期",
                        summary="新批次",
                        published_at=datetime(2026, 3, 20, 9, 0, tzinfo=UTC),
                        url="https://example.com/stock-archive",
                        publisher="测试源",
                        source="eastmoney_stock",
                        fetched_at=datetime(2026, 3, 21, 9, 5, tzinfo=UTC),
                    ),
                    NewsEvent(
                        id="policy-single",
                        scope="policy",
                        cache_variant="policy_source",
                        ts_code=None,
                        symbol=None,
                        title="白酒行业监管新规",
                        summary="政策摘要",
                        published_at=datetime(2026, 3, 22, 10, 0, tzinfo=UTC),
                        url="https://example.com/policy-single",
                        publisher="政策源",
                        source="policy_gateway",
                        macro_topic="regulation_policy",
                        fetched_at=datetime(2026, 3, 22, 10, 5, tzinfo=UTC),
                    ),
                ]
            )
            await session.commit()

            rows = await load_recent_news_events(
                session,
                "600519.SH",
                topic=None,
                anchor_event_id=None,
                published_from=None,
                published_to=None,
                limit=10,
            )

            assert len(rows) == 2
            assert rows[0].title == "白酒行业监管新规"
            assert rows[1].summary == "新批次"

    try:
        asyncio.run(run_test())
    finally:
        asyncio.run(engine.dispose())
