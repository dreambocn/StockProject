import asyncio

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from conftest import build_sqlite_test_context, init_sqlite_schema

from app.db.base import Base
from app.models.analysis_generation_session import AnalysisGenerationSession
from app.models.stock_instrument import StockInstrument
from app.models.system_job_run import SystemJobRun
from app.services.analysis_service import run_analysis_session_by_id, start_analysis_session


def test_analysis_session_creates_and_completes_system_job(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_file = tmp_path / "analysis-job.db"
    engine, session_maker = build_sqlite_test_context(tmp_path, "analysis-job.db")
    monkeypatch.setattr("app.services.analysis_service.SessionLocal", session_maker)

    async def run_test() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

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
            await session.commit()

            result = await start_analysis_session(
                session,
                "600519.SH",
                topic=None,
                event_id=None,
                force_refresh=False,
                use_web_search=False,
                trigger_source="manual",
                execute_inline=False,
            )
            assert result["session_id"] is not None

            session_row = (
                await session.execute(select(AnalysisGenerationSession).limit(1))
            ).scalar_one()
            job_row = (
                await session.execute(select(SystemJobRun).limit(1))
            ).scalar_one()
            assert session_row.system_job_id == job_row.id
            assert job_row.job_type == "analysis_generate"
            assert job_row.status == "queued"

        await run_analysis_session_by_id(str(result["session_id"]))

        async with session_maker() as session:
            job_row = (
                await session.execute(select(SystemJobRun).limit(1))
            ).scalar_one()
            session_row = (
                await session.execute(select(AnalysisGenerationSession).limit(1))
            ).scalar_one()
            assert session_row.report_id is not None
            assert job_row.linked_entity_id == session_row.id
            assert job_row.status in {"success", "partial"}


    asyncio.run(run_test())
