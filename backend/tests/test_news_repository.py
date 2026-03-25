import asyncio
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models.news_event import NewsEvent
from app.schemas.news import (
    HotNewsItemResponse,
    NewsEventResponse,
    StockRelatedNewsItemResponse,
)
from app.services.news_repository import (
    load_hot_news_rows_from_db,
    load_policy_news_rows,
    load_stock_news_rows_from_db,
    query_news_events,
    replace_hot_news_rows,
    replace_policy_news_rows,
    replace_stock_news_rows,
)
from app.services.news_latest_query_service import (
    build_latest_news_events_statement,
)


def _setup_async_session(tmp_path: Path):
    db_path = tmp_path / "news-repository.db"
    db_url = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    engine = create_async_engine(db_url)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    async def _create_tables() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(_create_tables())
    return engine, session_maker


def test_replace_news_rows_archives_batches_but_latest_readers_only_return_latest_batch(
    tmp_path: Path,
) -> None:
    engine, session_maker = _setup_async_session(tmp_path)

    async def run_test() -> None:
        async with session_maker() as session:
            await replace_hot_news_rows(
                session=session,
                cache_variant="global",
                fetched_at=datetime(2026, 3, 3, 10, 5, tzinfo=UTC),
                rows=[
                    HotNewsItemResponse(
                        event_id="hot-v1",
                        cluster_key="hot-oil",
                        providers=["akshare"],
                        source_coverage="AK",
                        title="旧热点批次",
                        summary="旧热点摘要",
                        published_at=datetime(2026, 3, 3, 10, 0, tzinfo=UTC),
                        url="https://example.com/hot-v1",
                        source="eastmoney_global",
                        macro_topic="commodity_supply",
                    )
                ],
            )
            await replace_hot_news_rows(
                session=session,
                cache_variant="global",
                fetched_at=datetime(2026, 3, 4, 10, 5, tzinfo=UTC),
                rows=[
                    HotNewsItemResponse(
                        event_id="hot-v2",
                        cluster_key="hot-oil",
                        providers=["akshare"],
                        source_coverage="AK",
                        title="新热点批次",
                        summary="新热点摘要",
                        published_at=datetime(2026, 3, 4, 10, 0, tzinfo=UTC),
                        url="https://example.com/hot-v2",
                        source="eastmoney_global",
                        macro_topic="commodity_supply",
                    )
                ],
            )
            await replace_policy_news_rows(
                session=session,
                fetched_at=datetime(2026, 3, 2, 10, 5, tzinfo=UTC),
                rows=[
                    NewsEventResponse(
                        scope="policy",
                        cache_variant="policy_source",
                        ts_code=None,
                        symbol=None,
                        title="旧政策批次",
                        summary="旧政策摘要",
                        published_at=datetime(2026, 3, 2, 10, 0, tzinfo=UTC),
                        url="https://example.com/policy-v1",
                        publisher="政策源",
                        source="policy_gateway",
                        macro_topic="regulation_policy",
                        fetched_at=datetime(2026, 3, 2, 10, 5, tzinfo=UTC),
                    )
                ],
            )
            await replace_policy_news_rows(
                session=session,
                fetched_at=datetime(2026, 3, 5, 10, 5, tzinfo=UTC),
                rows=[
                    NewsEventResponse(
                        scope="policy",
                        cache_variant="policy_source",
                        ts_code=None,
                        symbol=None,
                        title="新政策批次",
                        summary="新政策摘要",
                        published_at=datetime(2026, 3, 5, 10, 0, tzinfo=UTC),
                        url="https://example.com/policy-v2",
                        publisher="政策源",
                        source="policy_gateway",
                        macro_topic="regulation_policy",
                        fetched_at=datetime(2026, 3, 5, 10, 5, tzinfo=UTC),
                    )
                ],
            )
            await replace_stock_news_rows(
                session=session,
                ts_code="600029.SH",
                symbol="600029",
                cache_variant="with_announcements",
                fetched_at=datetime(2026, 3, 3, 9, 5, tzinfo=UTC),
                rows=[
                    StockRelatedNewsItemResponse(
                        ts_code="600029.SH",
                        symbol="600029",
                        title="旧个股批次",
                        summary="旧个股摘要",
                        published_at=datetime(2026, 3, 3, 9, 0, tzinfo=UTC),
                        url="https://example.com/stock-v1",
                        publisher="证券时报",
                        source="eastmoney_stock",
                    )
                ],
            )
            await replace_stock_news_rows(
                session=session,
                ts_code="600029.SH",
                symbol="600029",
                cache_variant="with_announcements",
                fetched_at=datetime(2026, 3, 4, 9, 5, tzinfo=UTC),
                rows=[
                    StockRelatedNewsItemResponse(
                        ts_code="600029.SH",
                        symbol="600029",
                        title="新个股批次",
                        summary="新个股摘要",
                        published_at=datetime(2026, 3, 4, 9, 0, tzinfo=UTC),
                        url="https://example.com/stock-v2",
                        publisher="证券时报",
                        source="eastmoney_stock",
                    )
                ],
            )
            await session.commit()

            hot_total = await session.scalar(
                select(func.count()).select_from(NewsEvent).where(NewsEvent.scope == "hot")
            )
            policy_total = await session.scalar(
                select(func.count()).select_from(NewsEvent).where(NewsEvent.scope == "policy")
            )
            stock_total = await session.scalar(
                select(func.count()).select_from(NewsEvent).where(NewsEvent.scope == "stock")
            )
            assert hot_total == 2
            assert policy_total == 2
            assert stock_total == 2

            hot_rows = await load_hot_news_rows_from_db(
                session=session,
                cache_variant="global",
                topic="all",
                limit=10,
            )
            policy_rows = await load_policy_news_rows(session=session, limit=10)
            stock_rows = await load_stock_news_rows_from_db(
                session=session,
                ts_code="600029.SH",
                cache_variant="with_announcements",
                limit=10,
            )

            assert [item.title for item in hot_rows] == ["新热点批次"]
            assert [item.title for item in policy_rows] == ["新政策批次"]
            assert [item.title for item in stock_rows] == ["新个股批次"]

    try:
        asyncio.run(run_test())
    finally:
        asyncio.run(engine.dispose())


def test_query_news_events_supports_latest_and_all_batch_modes(
    tmp_path: Path,
) -> None:
    engine, session_maker = _setup_async_session(tmp_path)

    async def run_test() -> None:
        async with session_maker() as session:
            session.add_all(
                [
                    NewsEvent(
                        id="stock-v1",
                        scope="stock",
                        cache_variant="with_announcements",
                        ts_code="600029.SH",
                        symbol="600029",
                        title="南方航空发布运力恢复公告",
                        summary="旧批次",
                        published_at=datetime(2026, 3, 3, 9, 0, tzinfo=UTC),
                        url="https://example.com/stock",
                        publisher="证券时报",
                        source="eastmoney_stock",
                        fetched_at=datetime(2026, 3, 3, 9, 5, tzinfo=UTC),
                    ),
                    NewsEvent(
                        id="stock-v2",
                        scope="stock",
                        cache_variant="with_announcements",
                        ts_code="600029.SH",
                        symbol="600029",
                        title="南方航空发布运力恢复公告",
                        summary="新批次",
                        published_at=datetime(2026, 3, 3, 9, 0, tzinfo=UTC),
                        url="https://example.com/stock",
                        publisher="证券时报",
                        source="eastmoney_stock",
                        fetched_at=datetime(2026, 3, 4, 9, 5, tzinfo=UTC),
                    ),
                    NewsEvent(
                        id="policy-v1",
                        scope="policy",
                        cache_variant="policy_source",
                        ts_code=None,
                        symbol=None,
                        title="监管政策更新",
                        summary="政策摘要",
                        published_at=datetime(2026, 3, 5, 10, 0, tzinfo=UTC),
                        url="https://example.com/policy",
                        publisher="政策源",
                        source="policy_gateway",
                        cluster_key="policy-cluster",
                        macro_topic="regulation_policy",
                        fetched_at=datetime(2026, 3, 5, 10, 5, tzinfo=UTC),
                    ),
                ]
            )
            await session.commit()

            latest_rows = await query_news_events(
                session=session,
                scope=None,
                ts_code=None,
                topic=None,
                published_from=None,
                published_to=None,
                limit=10,
                offset=0,
                batch_mode="latest",
            )
            all_rows = await query_news_events(
                session=session,
                scope=None,
                ts_code=None,
                topic=None,
                published_from=None,
                published_to=None,
                limit=10,
                offset=0,
                batch_mode="all",
            )

            stock_latest_rows = [
                item for item in latest_rows if item.title == "南方航空发布运力恢复公告"
            ]
            stock_all_rows = [
                item for item in all_rows if item.title == "南方航空发布运力恢复公告"
            ]

            assert len(stock_latest_rows) == 1
            assert stock_latest_rows[0].summary == "新批次"
            assert len(stock_all_rows) == 2
            assert stock_all_rows[0].summary == "新批次"
            assert stock_all_rows[1].summary == "旧批次"

    try:
        asyncio.run(run_test())
    finally:
        asyncio.run(engine.dispose())


def test_latest_query_service_selects_latest_rows_for_cluster_and_fallback(
    tmp_path: Path,
) -> None:
    engine, session_maker = _setup_async_session(tmp_path)

    async def run_test() -> None:
        async with session_maker() as session:
            session.add_all(
                [
                    NewsEvent(
                        id="hot-old",
                        scope="hot",
                        cache_variant="global",
                        ts_code=None,
                        symbol=None,
                        title="国际油价波动",
                        summary="旧批次",
                        published_at=datetime(2026, 3, 5, 9, 0, tzinfo=UTC),
                        url="https://example.com/hot",
                        publisher="测试源",
                        source="eastmoney_global",
                        cluster_key="hot-cluster-1",
                        fetched_at=datetime(2026, 3, 5, 9, 5, tzinfo=UTC),
                    ),
                    NewsEvent(
                        id="hot-new",
                        scope="hot",
                        cache_variant="global",
                        ts_code=None,
                        symbol=None,
                        title="国际油价波动",
                        summary="新批次",
                        published_at=datetime(2026, 3, 5, 9, 0, tzinfo=UTC),
                        url="https://example.com/hot",
                        publisher="测试源",
                        source="eastmoney_global",
                        cluster_key="hot-cluster-1",
                        fetched_at=datetime(2026, 3, 6, 9, 5, tzinfo=UTC),
                    ),
                    NewsEvent(
                        id="stock-old",
                        scope="stock",
                        cache_variant="with_announcements",
                        ts_code="600029.SH",
                        symbol="600029",
                        title="南方航空公告",
                        summary="旧批次",
                        published_at=datetime(2026, 3, 4, 9, 0, tzinfo=UTC),
                        url="https://example.com/stock",
                        publisher="测试源",
                        source="eastmoney_stock",
                        cluster_key=None,
                        fetched_at=datetime(2026, 3, 4, 9, 5, tzinfo=UTC),
                    ),
                    NewsEvent(
                        id="stock-new",
                        scope="stock",
                        cache_variant="with_announcements",
                        ts_code="600029.SH",
                        symbol="600029",
                        title="南方航空公告",
                        summary="新批次",
                        published_at=datetime(2026, 3, 4, 9, 0, tzinfo=UTC),
                        url="https://example.com/stock",
                        publisher="测试源",
                        source="eastmoney_stock",
                        cluster_key="  ",
                        fetched_at=datetime(2026, 3, 5, 9, 5, tzinfo=UTC),
                    ),
                ]
            )
            await session.commit()

            latest_statement = build_latest_news_events_statement(
                base_statement=select(NewsEvent),
                apply_default_order=True,
            )
            rows = (await session.execute(latest_statement)).scalars().all()

            assert [item.id for item in rows] == ["hot-new", "stock-new"]
            assert [item.summary for item in rows] == ["新批次", "新批次"]

    try:
        asyncio.run(run_test())
    finally:
        asyncio.run(engine.dispose())


def test_latest_query_service_paginates_after_dedupe(
    tmp_path: Path,
) -> None:
    engine, session_maker = _setup_async_session(tmp_path)

    async def run_test() -> None:
        async with session_maker() as session:
            session.add_all(
                [
                    NewsEvent(
                        id="evt-a-old",
                        scope="hot",
                        cache_variant="global",
                        ts_code=None,
                        symbol=None,
                        title="事件A",
                        summary="旧批次A",
                        published_at=datetime(2026, 3, 1, 10, 0, tzinfo=UTC),
                        url="https://example.com/a",
                        publisher="测试源",
                        source="eastmoney_global",
                        cluster_key="cluster-a",
                        fetched_at=datetime(2026, 3, 1, 10, 5, tzinfo=UTC),
                    ),
                    NewsEvent(
                        id="evt-a-new",
                        scope="hot",
                        cache_variant="global",
                        ts_code=None,
                        symbol=None,
                        title="事件A",
                        summary="新批次A",
                        published_at=datetime(2026, 3, 1, 10, 0, tzinfo=UTC),
                        url="https://example.com/a",
                        publisher="测试源",
                        source="eastmoney_global",
                        cluster_key="cluster-a",
                        fetched_at=datetime(2026, 3, 2, 10, 5, tzinfo=UTC),
                    ),
                    NewsEvent(
                        id="evt-b-new",
                        scope="hot",
                        cache_variant="global",
                        ts_code=None,
                        symbol=None,
                        title="事件B",
                        summary="新批次B",
                        published_at=datetime(2026, 3, 3, 10, 0, tzinfo=UTC),
                        url="https://example.com/b",
                        publisher="测试源",
                        source="eastmoney_global",
                        cluster_key="cluster-b",
                        fetched_at=datetime(2026, 3, 3, 10, 5, tzinfo=UTC),
                    ),
                ]
            )
            await session.commit()

            latest_statement = build_latest_news_events_statement(
                base_statement=select(NewsEvent),
                apply_default_order=True,
            )
            paged_rows = (
                await session.execute(latest_statement.offset(1).limit(1))
            ).scalars().all()

            assert len(paged_rows) == 1
            assert paged_rows[0].id == "evt-a-new"

    try:
        asyncio.run(run_test())
    finally:
        asyncio.run(engine.dispose())
