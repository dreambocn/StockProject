import asyncio
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models.analysis_event_link import AnalysisEventLink
from app.models.analysis_report import AnalysisReport
from app.models.news_event import NewsEvent
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
    session.add(
        StockInstrument(
            ts_code=ts_code,
            symbol="000001",
            name="测试公司",
            fullname="测试公司全称",
            list_status="L",
        )
    )
    session.add(
        NewsEvent(
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
    )
    session.add(
        AnalysisEventLink(
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
    )
    session.add(
        AnalysisReport(
            ts_code=ts_code,
            status="ready",
            summary="测试报告",
            risk_points=["风险1", "风险2"],
            factor_breakdown=[
                {
                    "factor_key": "policy",
                    "factor_label": "政策",
                    "weight": 0.5,
                    "direction": "positive",
                    "evidence": ["证据1"],
                    "reason": "政策利好",
                }
            ],
            generated_at=datetime.now(timezone.utc),
        )
    )
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
