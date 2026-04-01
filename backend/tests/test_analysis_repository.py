import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models.analysis_event_link import AnalysisEventLink
from app.models.news_event import NewsEvent
from app.services.analysis_repository import load_analysis_events, load_recent_news_events


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


def test_load_recent_news_events_keeps_anchor_event_first(tmp_path: Path) -> None:
    engine, session_maker = _setup_async_session(tmp_path)

    async def run_test() -> None:
        async with session_maker() as session:
            session.add_all(
                [
                    NewsEvent(
                        id="anchor-old",
                        scope="stock",
                        cache_variant="with_announcements",
                        ts_code="600519.SH",
                        symbol="600519",
                        title="贵州茅台业绩增长超预期",
                        summary="旧批次锚点",
                        published_at=datetime(2026, 3, 20, 9, 0, tzinfo=UTC),
                        url="https://example.com/anchor",
                        publisher="测试源",
                        source="eastmoney_stock",
                        cluster_key="stock-cluster-1",
                        fetched_at=datetime(2026, 3, 20, 9, 5, tzinfo=UTC),
                    ),
                    NewsEvent(
                        id="anchor-new",
                        scope="stock",
                        cache_variant="with_announcements",
                        ts_code="600519.SH",
                        symbol="600519",
                        title="贵州茅台业绩增长超预期",
                        summary="新批次锚点",
                        published_at=datetime(2026, 3, 20, 9, 0, tzinfo=UTC),
                        url="https://example.com/anchor",
                        publisher="测试源",
                        source="eastmoney_stock",
                        cluster_key="stock-cluster-1",
                        fetched_at=datetime(2026, 3, 21, 9, 5, tzinfo=UTC),
                    ),
                    NewsEvent(
                        id="policy-latest",
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
                anchor_event_id="anchor-old",
                published_from=None,
                published_to=None,
                limit=10,
            )

            assert len(rows) == 2
            assert rows[0].id == "anchor-old"
            assert rows[1].id == "policy-latest"

    try:
        asyncio.run(run_test())
    finally:
        asyncio.run(engine.dispose())


def test_load_recent_news_events_candidate_limit_returns_larger_candidate_pool(
    tmp_path: Path,
) -> None:
    engine, session_maker = _setup_async_session(tmp_path)

    async def run_test() -> None:
        async with session_maker() as session:
            base_time = datetime(2026, 3, 25, 12, 0, tzinfo=UTC)
            session.add_all(
                [
                    NewsEvent(
                        id=f"stock-{index}",
                        scope="stock",
                        cache_variant="with_announcements",
                        ts_code="600519.SH",
                        symbol="600519",
                        title=f"个股事件 {index}",
                        summary="候选池事件",
                        published_at=base_time - timedelta(minutes=index),
                        url=f"https://example.com/stock-{index}",
                        publisher="测试源",
                        source="eastmoney_stock",
                        fetched_at=base_time - timedelta(minutes=index),
                    )
                    for index in range(4)
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
                limit=1,
                candidate_limit=3,
            )

            assert len(rows) == 3

    try:
        asyncio.run(run_test())
    finally:
        asyncio.run(engine.dispose())


def test_load_recent_news_events_includes_hot_context_when_topic_missing(
    tmp_path: Path,
) -> None:
    engine, session_maker = _setup_async_session(tmp_path)

    async def run_test() -> None:
        async with session_maker() as session:
            base_time = datetime(2026, 4, 1, 12, 0, tzinfo=UTC)
            session.add_all(
                [
                    NewsEvent(
                        id='stock-1',
                        scope='stock',
                        cache_variant='with_announcements',
                        ts_code='000001.SZ',
                        symbol='000001',
                        title='个股事件',
                        summary='个股摘要',
                        published_at=base_time - timedelta(minutes=3),
                        url='https://example.com/stock-1',
                        publisher='测试源',
                        source='eastmoney_stock',
                        fetched_at=base_time - timedelta(minutes=3),
                    ),
                    NewsEvent(
                        id='policy-1',
                        scope='policy',
                        cache_variant='policy_source',
                        ts_code=None,
                        symbol=None,
                        title='政策事件',
                        summary='政策摘要',
                        published_at=base_time - timedelta(minutes=2),
                        url='https://example.com/policy-1',
                        publisher='政策源',
                        source='miit',
                        macro_topic='industrial_policy',
                        fetched_at=base_time - timedelta(minutes=2),
                    ),
                    NewsEvent(
                        id='hot-1',
                        scope='hot',
                        cache_variant='global',
                        ts_code=None,
                        symbol=None,
                        title='热点事件',
                        summary='热点摘要',
                        published_at=base_time - timedelta(minutes=1),
                        url='https://example.com/hot-1',
                        publisher='热点源',
                        source='eastmoney_global',
                        macro_topic='commodity_supply',
                        fetched_at=base_time,
                    ),
                ]
            )
            await session.commit()

            rows = await load_recent_news_events(
                session,
                '000001.SZ',
                topic=None,
                anchor_event_id=None,
                published_from=None,
                published_to=None,
                limit=10,
            )

            assert {row.scope for row in rows} == {'stock', 'policy', 'hot'}

    try:
        asyncio.run(run_test())
    finally:
        asyncio.run(engine.dispose())


def test_load_analysis_events_candidate_limit_supports_summary_oversampling(
    tmp_path: Path,
) -> None:
    engine, session_maker = _setup_async_session(tmp_path)

    async def run_test() -> None:
        async with session_maker() as session:
            base_time = datetime(2026, 3, 25, 12, 0, tzinfo=UTC)
            session.add_all(
                [
                    NewsEvent(
                        id=f"event-{index}",
                        scope="stock",
                        cache_variant="default",
                        ts_code="600519.SH",
                        symbol="600519",
                        title=f"摘要事件 {index}",
                        summary="摘要候选",
                        published_at=base_time - timedelta(minutes=index),
                        url=f"https://example.com/summary-{index}",
                        publisher="测试源",
                        source="eastmoney_stock",
                        fetched_at=base_time - timedelta(minutes=index),
                    )
                    for index in range(4)
                ]
            )
            session.add_all(
                [
                    AnalysisEventLink(
                        event_id=f"event-{index}",
                        ts_code="600519.SH",
                        created_at=base_time - timedelta(minutes=index),
                    )
                    for index in range(4)
                ]
            )
            await session.commit()

            rows = await load_analysis_events(
                session,
                "600519.SH",
                limit=1,
                candidate_limit=3,
            )

            assert len(rows) == 3
            assert rows[0]["event_id"] == "event-0"

    try:
        asyncio.run(run_test())
    finally:
        asyncio.run(engine.dispose())
