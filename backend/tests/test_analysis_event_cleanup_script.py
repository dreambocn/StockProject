import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models.analysis_event_link import AnalysisEventLink
from app.models.analysis_generation_session import AnalysisGenerationSession
from app.models.analysis_report import AnalysisReport
from app.models.news_event import NewsEvent
from scripts.dedupe_analysis_event_links import dedupe_analysis_event_links


def _setup_async_session(tmp_path: Path):
    db_path = tmp_path / "analysis-event-cleanup.db"
    db_url = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    engine = create_async_engine(db_url)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    async def _create_tables() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(_create_tables())
    return engine, session_maker


def test_dedupe_analysis_event_links_dry_run_keeps_rows(tmp_path: Path) -> None:
    engine, session_maker = _setup_async_session(tmp_path)

    async def run_test() -> None:
        base_time = datetime(2026, 3, 25, 12, 0, tzinfo=UTC)
        async with session_maker() as session:
            session.add(
                AnalysisReport(
                    id="report-1",
                    ts_code="600519.SH",
                    status="ready",
                    summary="测试报告",
                    risk_points=[],
                    factor_breakdown=[],
                    generated_at=base_time,
                )
            )
            session.add(
                AnalysisGenerationSession(
                    id="session-1",
                    analysis_key="analysis-key",
                    ts_code="600519.SH",
                    status="completed",
                    report_id="report-1",
                )
            )
            session.add_all(
                [
                    NewsEvent(
                        id="evt-old",
                        scope="stock",
                        cache_variant="default",
                        ts_code="600519.SH",
                        title="重复事件",
                        summary="旧批次",
                        published_at=base_time - timedelta(hours=1),
                        url="https://example.com/duplicate",
                        publisher="测试源",
                        source="stock-source",
                        cluster_key="duplicate-cluster",
                        fetched_at=base_time - timedelta(hours=1),
                    ),
                    NewsEvent(
                        id="evt-new",
                        scope="stock",
                        cache_variant="default",
                        ts_code="600519.SH",
                        title="重复事件",
                        summary="新批次",
                        published_at=base_time - timedelta(hours=1),
                        url="https://example.com/duplicate",
                        publisher="测试源",
                        source="stock-source",
                        cluster_key="duplicate-cluster",
                        fetched_at=base_time,
                    ),
                ]
            )
            session.add_all(
                [
                    AnalysisEventLink(
                        event_id="evt-old",
                        ts_code="600519.SH",
                        created_at=base_time - timedelta(minutes=5),
                    ),
                    AnalysisEventLink(
                        event_id="evt-new",
                        ts_code="600519.SH",
                        created_at=base_time,
                    ),
                ]
            )
            await session.commit()

            result = await dedupe_analysis_event_links(
                session,
                analysis_report_id="report-1",
                apply_changes=False,
            )
            rows = (
                await session.execute(
                    select(AnalysisEventLink).where(
                        AnalysisEventLink.ts_code == "600519.SH"
                    )
                )
            ).scalars().all()

            assert result["duplicate_groups"] == 1
            assert result["deleted_rows"] == 0
            assert len(rows) == 2

    try:
        asyncio.run(run_test())
    finally:
        asyncio.run(engine.dispose())


def test_dedupe_analysis_event_links_apply_keeps_latest_row(tmp_path: Path) -> None:
    engine, session_maker = _setup_async_session(tmp_path)

    async def run_test() -> None:
        base_time = datetime(2026, 3, 25, 12, 0, tzinfo=UTC)
        async with session_maker() as session:
            session.add(
                AnalysisReport(
                    id="report-1",
                    ts_code="600519.SH",
                    status="ready",
                    summary="测试报告",
                    risk_points=[],
                    factor_breakdown=[],
                    generated_at=base_time,
                )
            )
            session.add(
                AnalysisGenerationSession(
                    id="session-1",
                    analysis_key="analysis-key",
                    ts_code="600519.SH",
                    status="completed",
                    report_id="report-1",
                )
            )
            session.add_all(
                [
                    NewsEvent(
                        id="evt-old",
                        scope="stock",
                        cache_variant="default",
                        ts_code="600519.SH",
                        title="重复事件",
                        summary="旧批次",
                        published_at=base_time - timedelta(hours=1),
                        url="https://example.com/duplicate",
                        publisher="测试源",
                        source="stock-source",
                        fetched_at=base_time - timedelta(hours=1),
                    ),
                    NewsEvent(
                        id="evt-new",
                        scope="stock",
                        cache_variant="default",
                        ts_code="600519.SH",
                        title="重复事件",
                        summary="新批次",
                        published_at=base_time - timedelta(hours=1),
                        url="https://example.com/duplicate",
                        publisher="测试源",
                        source="stock-source",
                        fetched_at=base_time,
                    ),
                ]
            )
            session.add_all(
                [
                    AnalysisEventLink(
                        event_id="evt-old",
                        ts_code="600519.SH",
                        created_at=base_time - timedelta(minutes=5),
                    ),
                    AnalysisEventLink(
                        event_id="evt-new",
                        ts_code="600519.SH",
                        created_at=base_time,
                    ),
                ]
            )
            await session.commit()

            result = await dedupe_analysis_event_links(
                session,
                analysis_report_id="report-1",
                apply_changes=True,
            )
            rows = (
                await session.execute(
                    select(AnalysisEventLink).where(
                        AnalysisEventLink.ts_code == "600519.SH"
                    )
                )
            ).scalars().all()

            assert result["duplicate_groups"] == 1
            assert result["deleted_rows"] == 1
            assert [row.event_id for row in rows] == ["evt-new"]

    try:
        asyncio.run(run_test())
    finally:
        asyncio.run(engine.dispose())
