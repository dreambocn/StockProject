import asyncio
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from conftest import build_sqlite_test_context, init_sqlite_schema

from app.db.base import Base
from app.db.session import get_db_session
from app.main import app
from app.models.analysis_agent_run import AnalysisAgentRun
from app.models.analysis_report import AnalysisReport


def _create_export_context(tmp_path: Path):
    engine, session_maker = build_sqlite_test_context(tmp_path, "analysis-export.db")
    init_sqlite_schema(engine)

    async def override_get_db_session():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session
    return engine, session_maker, TestClient(app)


def _cleanup_export_context(engine) -> None:
    app.dependency_overrides.clear()


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


def test_analysis_export_route_includes_pipeline_roles_for_functional_report(
    tmp_path: Path,
) -> None:
    engine, session_maker, client = _create_export_context(tmp_path)
    try:
        async def _seed() -> None:
            async with session_maker() as session:
                session.add(
                    AnalysisReport(
                        id="functional-export-report",
                        ts_code="600519.SH",
                        status="ready",
                        summary="## 核心判断\n采用偏多假设。",
                        risk_points=["关注公告兑现节奏"],
                        factor_breakdown=[],
                        analysis_mode="functional_multi_agent",
                        selected_hypothesis="bullish_hypothesis",
                        decision_confidence="high",
                        decision_reason_summary="正向证据更强。",
                        generated_at=datetime(2026, 4, 12, 10, 0, tzinfo=UTC),
                    )
                )
                session.add(
                    AnalysisAgentRun(
                        session_id="functional-session-1",
                        report_id="functional-export-report",
                        role_key="research_planner",
                        role_label="研究规划",
                        status="completed",
                        sort_order=1,
                        summary="已生成研究计划",
                        output_payload={"focus_buckets": ["stock_news", "announcements"]},
                    )
                )
                await session.commit()

        asyncio.run(_seed())

        response = client.get("/api/analysis/reports/functional-export-report/export?format=markdown")
        assert response.status_code == 200
        assert "采纳假设" in response.text
        assert "研究流水线" in response.text
        assert "研究规划" in response.text
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
