import asyncio
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.session import get_db_session
from app.main import app
from app.models.analysis_report import AnalysisReport


def _create_export_context(tmp_path: Path):
    db_path = tmp_path / "analysis-export.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path.as_posix()}")
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    async def _create_tables() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(_create_tables())

    async def override_get_db_session():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session
    return engine, session_maker, TestClient(app)


def _cleanup_export_context(engine) -> None:
    app.dependency_overrides.clear()
    asyncio.run(engine.dispose())


def test_analysis_export_route_returns_markdown_and_html(tmp_path: Path) -> None:
    engine, session_maker, client = _create_export_context(tmp_path)
    try:
        async def _seed() -> None:
            async with session_maker() as session:
                session.add(
                    AnalysisReport(
                        id="report-1",
                        ts_code="600519.SH",
                        status="ready",
                        summary="## 核心判断\n测试摘要",
                        risk_points=["风险一"],
                        factor_breakdown=[{"factor_label": "景气", "weight": 0.5, "reason": "景气上行"}],
                        structured_sources=[{"provider": "akshare", "count": 2}],
                        web_sources=[{"title": "外部来源", "url": "https://example.com/a"}],
                        generated_at=datetime(2026, 3, 31, 10, 0, tzinfo=UTC),
                    )
                )
                await session.commit()

        asyncio.run(_seed())

        markdown_response = client.get("/api/analysis/reports/report-1/export?format=markdown")
        assert markdown_response.status_code == 200
        assert "## 风险提示" in markdown_response.text
        assert "外部来源" in markdown_response.text

        html_response = client.get("/api/analysis/reports/report-1/export?format=html")
        assert html_response.status_code == 200
        assert "<html" in html_response.text
        assert "结构化来源" in html_response.text
    finally:
        client.close()
        _cleanup_export_context(engine)


def test_analysis_export_route_returns_404_for_missing_report(tmp_path: Path) -> None:
    engine, _session_maker, client = _create_export_context(tmp_path)
    try:
        response = client.get("/api/analysis/reports/not-found/export?format=markdown")
        assert response.status_code == 404
    finally:
        client.close()
        _cleanup_export_context(engine)
