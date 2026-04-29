import asyncio
from datetime import UTC, date, datetime
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker

from conftest import build_sqlite_test_context, init_sqlite_schema

from app.db.base import Base
from app.models.news_event import NewsEvent
from app.models.stock_instrument import StockInstrument
from app.services.news_mapper_service import (
    _load_anchor_events_by_topic,
    _load_relevant_candidate_instruments,
)


def test_load_anchor_events_by_topic_only_uses_latest_hot_fetch_window(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "news-mapper-test.db"
    engine, session_maker = build_sqlite_test_context(tmp_path, "news-mapper-test.db")

    async def _run() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        async with session_maker() as session:
            session.add_all(
                [
                    NewsEvent(
                        scope="hot",
                        cache_variant="global",
                        ts_code=None,
                        symbol=None,
                        title="旧批次但发布时间更晚的原油事件",
                        summary="这条旧数据不应再作为最新锚点",
                        published_at=datetime(2026, 3, 10, 9, 0, tzinfo=UTC),
                        url="https://example.com/old",
                        publisher=None,
                        source="eastmoney_global",
                        macro_topic="commodity_supply",
                        fetched_at=datetime(2026, 3, 1, 10, 0, tzinfo=UTC),
                    ),
                    NewsEvent(
                        scope="hot",
                        cache_variant="global",
                        ts_code=None,
                        symbol=None,
                        title="最新批次原油事件",
                        summary="锚点事件应来自最新抓取窗口",
                        published_at=datetime(2026, 3, 5, 9, 0, tzinfo=UTC),
                        url="https://example.com/new",
                        publisher=None,
                        source="eastmoney_global",
                        macro_topic="commodity_supply",
                        fetched_at=datetime(2026, 3, 5, 10, 0, tzinfo=UTC),
                    ),
                ]
            )
            await session.commit()

            anchor_events = await _load_anchor_events_by_topic(
                session=session,
                topics={"commodity_supply"},
            )

            assert anchor_events["commodity_supply"]["title"] == "最新批次原油事件"

    asyncio.run(_run())


def test_load_relevant_candidate_instruments_only_returns_matching_rows(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "news-mapper-candidate-test.db"
    engine, session_maker = build_sqlite_test_context(tmp_path, "news-mapper-candidate-test.db")

    async def _run() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        async with session_maker() as session:
            session.add_all(
                [
                    StockInstrument(
                        ts_code="600938.SH",
                        symbol="600938",
                        name="中国海油",
                        fullname="中国海洋石油有限公司",
                        area="北京",
                        industry="石油开采",
                        market="主板",
                        exchange="SSE",
                        list_status="L",
                        list_date=date(2022, 4, 21),
                        delist_date=None,
                        is_hs="N",
                    ),
                    StockInstrument(
                        ts_code="600029.SH",
                        symbol="600029",
                        name="南方航空",
                        fullname="中国南方航空股份有限公司",
                        area="广东",
                        industry="航空运输",
                        market="主板",
                        exchange="SSE",
                        list_status="L",
                        list_date=date(2003, 7, 25),
                        delist_date=None,
                        is_hs="N",
                    ),
                    StockInstrument(
                        ts_code="000333.SZ",
                        symbol="000333",
                        name="美的集团",
                        fullname="美的集团股份有限公司",
                        area="广东",
                        industry="家用电器",
                        market="主板",
                        exchange="SZSE",
                        list_status="L",
                        list_date=date(2013, 9, 18),
                        delist_date=None,
                        is_hs="N",
                    ),
                ]
            )
            await session.commit()

            rows = await _load_relevant_candidate_instruments(
                session=session,
                target_names={"中国海油"},
                keywords={"航空"},
                recent_event_ts_codes={"000333.SZ"},
            )

            assert {item.ts_code for item in rows} == {
                "600938.SH",
                "600029.SH",
                "000333.SZ",
            }

    asyncio.run(_run())
