import asyncio
from datetime import datetime, timezone
from pathlib import Path
from decimal import Decimal

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.session import get_db_session
from app.main import app
from app.models.analysis_event_link import AnalysisEventLink
from app.models.analysis_report import AnalysisReport
from app.models.news_event import NewsEvent
from app.models.stock_daily_snapshot import StockDailySnapshot
from app.models.stock_instrument import StockInstrument
from app.services.analysis_service import get_stock_analysis_summary


def _setup_async_session(tmp_path: Path):
    db_path = tmp_path / "analysis-service.db"
    db_url = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    engine = create_async_engine(db_url)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    async def _create_tables() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(_create_tables())
    return engine, session_maker


async def _seed_analysis_data(session, ts_code: str, event_id: str):
    instrument = StockInstrument(
        ts_code=ts_code,
        symbol="000001",
        name="测试公司",
        fullname="测试公司全称",
        list_status="L",
    )
    session.add(instrument)
    event = NewsEvent(
        id=event_id,
        scope="stock",
        cache_variant="default",
        ts_code=ts_code,
        title="测试事件",
        summary="摘要",
        published_at=datetime.now(timezone.utc),
        url="https://example.com",
        publisher="测试",
        source="test-source",
        macro_topic="policy",
        fetched_at=datetime.now(timezone.utc),
    )
    session.add(event)
    link = AnalysisEventLink(
        event_id=event_id,
        ts_code=ts_code,
        anchor_trade_date=datetime.now(timezone.utc).date(),
        window_return_pct=1.2,
        window_volatility=0.4,
        abnormal_volume_ratio=1.5,
        correlation_score=0.8,
        confidence="high",
        link_status="linked",
    )
    session.add(link)
    report = AnalysisReport(
        ts_code=ts_code,
        status="ready",
        summary="测试报告",
        risk_points=["风险1", "风险2"],
        factor_breakdown=[{"factor_key": "policy", "factor_label": "政策", "weight": 0.5, "direction": "positive", "evidence": ["证据1"], "reason": "政策利好"}],
        generated_at=datetime.now(timezone.utc),
    )
    session.add(report)
    await session.commit()


def test_analysis_service_aggregates_events_and_report(tmp_path: Path) -> None:
    engine, session_maker = _setup_async_session(tmp_path)
    async def run_test():
        async with session_maker() as session:
            await _seed_analysis_data(session, "600519.SH", "event-1")
            result = await get_stock_analysis_summary(session, "600519.SH")
            assert result["ts_code"] == "600519.SH"
            assert result["event_count"] == 1
            assert result["events"][0]["event_id"] == "event-1"
            assert result["report"]["status"] == "ready"
            assert result["status"] == "ready"
    try:
        asyncio.run(run_test())
    finally:
        asyncio.run(engine.dispose())


def test_analysis_service_keeps_summary_read_only_before_session_generation(
    tmp_path: Path,
) -> None:
    engine, session_maker = _setup_async_session(tmp_path)

    async def run_test():
        async with session_maker() as session:
            session.add(
                StockInstrument(
                    ts_code="600519.SH",
                    symbol="600519",
                    name="贵州茅台",
                    fullname="贵州茅台酒股份有限公司",
                    list_status="L",
                )
            )
            session.add(
                NewsEvent(
                    id="raw-event-1",
                    scope="stock",
                    cache_variant="default",
                    ts_code="600519.SH",
                    symbol="600519",
                    title="贵州茅台业绩增长超预期",
                    summary="盈利能力持续提升",
                    published_at=datetime(2026, 3, 20, 9, 0, tzinfo=timezone.utc),
                    url="https://example.com/raw-event-1",
                    publisher="测试源",
                    source="eastmoney_stock",
                    macro_topic="regulation_policy",
                    fetched_at=datetime(2026, 3, 20, 9, 5, tzinfo=timezone.utc),
                )
            )
            session.add_all(
                [
                    StockDailySnapshot(
                        ts_code="600519.SH",
                        trade_date=datetime(2026, 3, 20, tzinfo=timezone.utc).date(),
                        close=Decimal("1500.00"),
                        vol=Decimal("1000"),
                    ),
                    StockDailySnapshot(
                        ts_code="600519.SH",
                        trade_date=datetime(2026, 3, 21, tzinfo=timezone.utc).date(),
                        close=Decimal("1528.00"),
                        vol=Decimal("1400"),
                    ),
                    StockDailySnapshot(
                        ts_code="600519.SH",
                        trade_date=datetime(2026, 3, 24, tzinfo=timezone.utc).date(),
                        close=Decimal("1536.00"),
                        vol=Decimal("1200"),
                    ),
                ]
            )
            await session.commit()

            result = await get_stock_analysis_summary(session, "600519.SH")

            # 新架构下 summary 为纯读取接口，不会在读取时即时生成事件关联与报告。
            assert result["event_count"] == 0
            assert result["events"] == []
            assert result["report"] is None
            assert result["status"] == "pending"

    try:
        asyncio.run(run_test())
    finally:
        asyncio.run(engine.dispose())


def test_analysis_service_filters_report_by_anchor_event_id(tmp_path: Path) -> None:
    engine, session_maker = _setup_async_session(tmp_path)

    async def run_test():
        async with session_maker() as session:
            session.add(
                StockInstrument(
                    ts_code="600519.SH",
                    symbol="600519",
                    name="贵州茅台",
                    fullname="贵州茅台酒股份有限公司",
                    list_status="L",
                )
            )
            session.add(
                NewsEvent(
                    id="evt-hot-1",
                    scope="hot",
                    cache_variant="global",
                    title="国际油价高位震荡",
                    summary="原油供需偏紧",
                    published_at=datetime(2026, 3, 3, 10, 0, tzinfo=timezone.utc),
                    url="https://example.com/hot-1",
                    publisher="测试源",
                    source="eastmoney_global",
                    macro_topic="commodity_supply",
                    fetched_at=datetime(2026, 3, 3, 10, 5, tzinfo=timezone.utc),
                )
            )
            session.add(
                AnalysisEventLink(
                    event_id="evt-hot-1",
                    ts_code="600519.SH",
                    correlation_score=0.91,
                    confidence="high",
                    link_status="linked",
                )
            )
            session.add_all(
                [
                    AnalysisReport(
                        ts_code="600519.SH",
                        status="ready",
                        summary="事件一报告",
                        risk_points=[],
                        factor_breakdown=[],
                        topic="commodity_supply",
                        anchor_event_id="evt-hot-1",
                        anchor_event_title="国际油价高位震荡",
                        structured_sources=[{"provider": "akshare", "count": 1}],
                        generated_at=datetime(2026, 3, 3, 10, 10, tzinfo=timezone.utc),
                    ),
                    AnalysisReport(
                        ts_code="600519.SH",
                        status="ready",
                        summary="普通主题报告",
                        risk_points=[],
                        factor_breakdown=[],
                        topic="commodity_supply",
                        anchor_event_id=None,
                        anchor_event_title=None,
                        structured_sources=[],
                        generated_at=datetime(2026, 3, 3, 10, 11, tzinfo=timezone.utc),
                    ),
                ]
            )
            await session.commit()

            result = await get_stock_analysis_summary(
                session,
                "600519.SH",
                topic="commodity_supply",
                event_id="evt-hot-1",
            )

            assert result["report"]["summary"] == "事件一报告"
            assert result["report"]["anchor_event_id"] == "evt-hot-1"
            assert result["report"]["structured_sources"] == [{"provider": "akshare", "count": 1}]

    try:
        asyncio.run(run_test())
    finally:
        asyncio.run(engine.dispose())
