import asyncio
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.services.analysis_service as analysis_service_module
from app.db.base import Base
from app.db.session import get_db_session
from app.main import app
from app.models.analysis_event_link import AnalysisEventLink
from app.models.analysis_generation_session import AnalysisGenerationSession
from app.models.analysis_report import AnalysisReport
from app.models.news_event import NewsEvent
from app.models.stock_daily_snapshot import StockDailySnapshot
from app.models.stock_instrument import StockInstrument
from app.services.llm_analysis_service import AnalysisReportResult
from app.services.analysis_service import (
    _build_structured_sources,
    get_stock_analysis_summary,
    list_stock_analysis_report_archives,
    run_analysis_session_by_id,
)


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


def test_build_structured_sources_marks_policy_document_provider() -> None:
    sources = _build_structured_sources(
        [
            {
                "scope": "policy",
                "source": "gov_cn",
                "event_type": "policy",
            },
            {
                "scope": "stock",
                "source": "eastmoney_stock",
                "event_type": "news",
            },
            {
                "scope": "hot",
                "source": "tushare_major_news",
                "event_type": "news",
            },
        ]
    )

    # 政策原文来源需要单独标识，避免与普通新闻来源混在一起。
    assert sources == [
        {"provider": "akshare", "count": 1},
        {"provider": "policy_document", "count": 1},
        {"provider": "tushare", "count": 1},
    ]


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


def test_analysis_service_backfills_web_source_metadata_on_summary_read(
    tmp_path: Path,
    monkeypatch,
) -> None:
    engine, session_maker = _setup_async_session(tmp_path)

    async def fake_enrich_web_sources(
        *,
        session,
        raw_sources,
        http_client=None,
        timeout_seconds=3,
        success_ttl_seconds=86400,
        failure_ttl_seconds=7200,
        max_bytes=1024 * 512,
    ):
        _ = session, http_client, timeout_seconds, success_ttl_seconds, failure_ttl_seconds, max_bytes
        return [
            {
                **raw_sources[0],
                "source": "Reuters",
                "published_at": "2026-03-24T09:30:00+00:00",
                "domain": "finance.example.com",
                "metadata_status": "enriched",
            }
        ]

    monkeypatch.setattr(
        "app.services.analysis_service.enrich_web_sources",
        fake_enrich_web_sources,
    )

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
                AnalysisReport(
                    ts_code="600519.SH",
                    status="ready",
                    summary="历史报告",
                    risk_points=[],
                    factor_breakdown=[],
                    web_sources=[
                        {
                            "title": "国际油价收涨",
                            "url": "https://finance.example.com/oil",
                            "source": None,
                            "published_at": None,
                            "snippet": "市场继续关注供给端扰动。",
                        }
                    ],
                    generated_at=datetime(2026, 3, 24, 10, 0, tzinfo=timezone.utc),
                )
            )
            await session.commit()

            result = await get_stock_analysis_summary(session, "600519.SH")

            assert result["report"]["web_sources"][0]["source"] == "Reuters"
            assert result["report"]["web_sources"][0]["domain"] == "finance.example.com"
            assert result["report"]["web_sources"][0]["metadata_status"] == "enriched"

            persisted_report = (
                await session.execute(select(AnalysisReport).where(AnalysisReport.ts_code == "600519.SH"))
            ).scalar_one()
            assert persisted_report.web_sources[0]["source"] == "Reuters"
            assert persisted_report.web_sources[0]["published_at"] == "2026-03-24T09:30:00+00:00"

    try:
        asyncio.run(run_test())
    finally:
        asyncio.run(engine.dispose())


def test_analysis_service_forces_domain_source_when_summary_backfill_unavailable(
    tmp_path: Path,
    monkeypatch,
) -> None:
    engine, session_maker = _setup_async_session(tmp_path)

    async def fake_enrich_web_sources(
        *,
        session,
        raw_sources,
        http_client=None,
        timeout_seconds=3,
        success_ttl_seconds=86400,
        failure_ttl_seconds=7200,
        max_bytes=1024 * 512,
    ):
        _ = session, http_client, timeout_seconds, success_ttl_seconds, failure_ttl_seconds, max_bytes
        return [
            {
                **raw_sources[0],
                "source": "LegacyWire",
                "published_at": "2026-03-01T09:30:00+00:00",
                "domain": "finance.example.com",
                "metadata_status": "unavailable",
            }
        ]

    monkeypatch.setattr(
        "app.services.analysis_service.enrich_web_sources",
        fake_enrich_web_sources,
    )

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
                AnalysisReport(
                    ts_code="600519.SH",
                    status="ready",
                    summary="历史报告",
                    risk_points=[],
                    factor_breakdown=[],
                    web_sources=[
                        {
                            "title": "国际油价收涨",
                            "url": "https://finance.example.com/oil",
                            "source": "LegacyWire",
                            "domain": "finance.example.com",
                            "published_at": "2026-03-01T09:30:00+00:00",
                            "metadata_status": "unavailable",
                            "snippet": "市场继续关注供给端扰动。",
                        }
                    ],
                    generated_at=datetime(2026, 3, 24, 10, 0, tzinfo=timezone.utc),
                )
            )
            await session.commit()

            result = await get_stock_analysis_summary(session, "600519.SH")
            current_source = result["report"]["web_sources"][0]
            assert current_source["metadata_status"] == "unavailable"
            assert current_source["source"] == "finance.example.com"
            assert current_source["published_at"] is None

            persisted_report = (
                await session.execute(select(AnalysisReport).where(AnalysisReport.ts_code == "600519.SH"))
            ).scalar_one()
            persisted_source = persisted_report.web_sources[0]
            assert persisted_source["metadata_status"] == "unavailable"
            assert persisted_source["source"] == "finance.example.com"
            assert persisted_source["published_at"] is None

    try:
        asyncio.run(run_test())
    finally:
        asyncio.run(engine.dispose())


def test_analysis_service_summary_backfill_respects_five_url_budget(
    tmp_path: Path,
    monkeypatch,
) -> None:
    engine, session_maker = _setup_async_session(tmp_path)
    called_sizes: list[int] = []

    async def fake_enrich_web_sources(
        *,
        session,
        raw_sources,
        http_client=None,
        timeout_seconds=3,
        success_ttl_seconds=86400,
        failure_ttl_seconds=7200,
        max_bytes=1024 * 512,
    ):
        _ = session, http_client, timeout_seconds, success_ttl_seconds, failure_ttl_seconds, max_bytes
        called_sizes.append(len(raw_sources))
        return [
            {
                **item,
                "source": "Reuters",
                "domain": "finance.example.com",
                "metadata_status": "enriched",
                "published_at": "2026-03-24T09:30:00+00:00",
            }
            for item in raw_sources
        ]

    monkeypatch.setattr(
        "app.services.analysis_service.enrich_web_sources",
        fake_enrich_web_sources,
    )

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
                AnalysisReport(
                    ts_code="600519.SH",
                    status="ready",
                    summary="历史报告",
                    risk_points=[],
                    factor_breakdown=[],
                    web_sources=[
                        {
                            "title": f"引用 {index}",
                            "url": f"https://finance.example.com/oil-{index}",
                            "source": None,
                            "domain": None,
                            "published_at": None,
                            "snippet": "市场继续关注供给端扰动。",
                        }
                        for index in range(8)
                    ],
                    generated_at=datetime(2026, 3, 24, 10, 0, tzinfo=timezone.utc),
                )
            )
            await session.commit()

            result = await get_stock_analysis_summary(session, "600519.SH")

            assert result["report"] is not None
            assert len(result["report"]["web_sources"]) == 8
            assert called_sizes == [5]

    try:
        asyncio.run(run_test())
    finally:
        asyncio.run(engine.dispose())


def test_analysis_service_reports_backfill_respects_three_three_ten_budget(
    tmp_path: Path,
    monkeypatch,
) -> None:
    engine, session_maker = _setup_async_session(tmp_path)
    called_sizes: list[int] = []

    async def fake_enrich_web_sources(
        *,
        session,
        raw_sources,
        http_client=None,
        timeout_seconds=3,
        success_ttl_seconds=86400,
        failure_ttl_seconds=7200,
        max_bytes=1024 * 512,
    ):
        _ = session, http_client, timeout_seconds, success_ttl_seconds, failure_ttl_seconds, max_bytes
        called_sizes.append(len(raw_sources))
        return [
            {
                **item,
                "source": "Reuters",
                "domain": "finance.example.com",
                "metadata_status": "enriched",
                "published_at": "2026-03-24T09:30:00+00:00",
            }
            for item in raw_sources
        ]

    monkeypatch.setattr(
        "app.services.analysis_service.enrich_web_sources",
        fake_enrich_web_sources,
    )

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
            base_time = datetime(2026, 3, 24, 10, 0, tzinfo=timezone.utc)
            for report_index in range(4):
                session.add(
                    AnalysisReport(
                        ts_code="600519.SH",
                        status="ready",
                        summary=f"历史报告 {report_index}",
                        risk_points=[],
                        factor_breakdown=[],
                        web_sources=[
                            {
                                "title": f"引用 {report_index}-{item_index}",
                                "url": f"https://finance.example.com/{report_index}-{item_index}",
                                "source": None,
                                "domain": None,
                                "published_at": None,
                                "snippet": "市场继续关注供给端扰动。",
                            }
                            for item_index in range(5)
                        ],
                        generated_at=base_time - timedelta(minutes=report_index),
                    )
                )
            await session.commit()

            result = await list_stock_analysis_report_archives(
                session,
                "600519.SH",
                limit=10,
            )

            assert len(result["items"]) == 4
            assert len(called_sizes) == 3
            assert all(size <= 3 for size in called_sizes)
            assert sum(called_sizes) <= 10

    try:
        asyncio.run(run_test())
    finally:
        asyncio.run(engine.dispose())


def test_analysis_service_skips_reenrichment_for_unavailable_fallback_ready_source(
    tmp_path: Path,
    monkeypatch,
) -> None:
    engine, session_maker = _setup_async_session(tmp_path)
    called_times = {"count": 0}

    async def fake_enrich_web_sources(
        *,
        session,
        raw_sources,
        http_client=None,
        timeout_seconds=3,
        success_ttl_seconds=86400,
        failure_ttl_seconds=7200,
        max_bytes=1024 * 512,
    ):
        _ = (
            session,
            raw_sources,
            http_client,
            timeout_seconds,
            success_ttl_seconds,
            failure_ttl_seconds,
            max_bytes,
        )
        called_times["count"] += 1
        return []

    monkeypatch.setattr(
        "app.services.analysis_service.enrich_web_sources",
        fake_enrich_web_sources,
    )

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
                AnalysisReport(
                    ts_code="600519.SH",
                    status="ready",
                    summary="历史报告",
                    risk_points=[],
                    factor_breakdown=[],
                    web_sources=[
                        {
                            "title": "国际油价收涨",
                            "url": "https://finance.example.com/oil",
                            "source": "finance.example.com",
                            "domain": "finance.example.com",
                            "published_at": None,
                            "metadata_status": "unavailable",
                            "snippet": "市场继续关注供给端扰动。",
                        }
                    ],
                    generated_at=datetime(2026, 3, 24, 10, 0, tzinfo=timezone.utc),
                )
            )
            await session.commit()

            first = await get_stock_analysis_summary(session, "600519.SH")
            second = await get_stock_analysis_summary(session, "600519.SH")

            assert first["report"] is not None
            assert second["report"] is not None
            assert called_times["count"] == 0

    try:
        asyncio.run(run_test())
    finally:
        asyncio.run(engine.dispose())


def test_analysis_service_summary_dedupes_duplicate_logical_events(tmp_path: Path) -> None:
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
            base_time = datetime(2026, 3, 25, 12, 0, tzinfo=timezone.utc)
            session.add_all(
                [
                    NewsEvent(
                        id="duplicate-old",
                        scope="stock",
                        cache_variant="default",
                        ts_code="600519.SH",
                        symbol="600519",
                        title="重复事件",
                        summary="旧批次",
                        published_at=base_time - timedelta(hours=1),
                        url="https://example.com/duplicate",
                        publisher="测试源",
                        source="eastmoney_stock",
                        cluster_key="duplicate-cluster",
                        fetched_at=base_time - timedelta(hours=1),
                    ),
                    NewsEvent(
                        id="duplicate-new",
                        scope="stock",
                        cache_variant="default",
                        ts_code="600519.SH",
                        symbol="600519",
                        title="重复事件",
                        summary="新批次",
                        published_at=base_time - timedelta(hours=1),
                        url="https://example.com/duplicate",
                        publisher="测试源",
                        source="eastmoney_stock",
                        cluster_key="duplicate-cluster",
                        fetched_at=base_time,
                    ),
                    NewsEvent(
                        id="unique-policy",
                        scope="policy",
                        cache_variant="policy_source",
                        title="政策事件",
                        summary="政策摘要",
                        published_at=base_time - timedelta(hours=2),
                        url="https://example.com/policy",
                        publisher="测试源",
                        source="policy-source",
                        macro_topic="commodity_supply",
                        fetched_at=base_time - timedelta(hours=2),
                    ),
                ]
            )
            session.add_all(
                [
                    AnalysisEventLink(
                        event_id="duplicate-old",
                        ts_code="600519.SH",
                        correlation_score=0.6,
                        created_at=base_time - timedelta(minutes=2),
                    ),
                    AnalysisEventLink(
                        event_id="duplicate-new",
                        ts_code="600519.SH",
                        correlation_score=0.9,
                        created_at=base_time - timedelta(minutes=1),
                    ),
                    AnalysisEventLink(
                        event_id="unique-policy",
                        ts_code="600519.SH",
                        correlation_score=0.5,
                        created_at=base_time,
                    ),
                ]
            )
            session.add(
                AnalysisReport(
                    ts_code="600519.SH",
                    status="ready",
                    summary="测试报告",
                    risk_points=[],
                    factor_breakdown=[],
                    generated_at=base_time,
                )
            )
            await session.commit()

            result = await get_stock_analysis_summary(session, "600519.SH")

            assert result["event_count"] == 2
            assert [item["event_id"] for item in result["events"]] == [
                "unique-policy",
                "duplicate-new",
            ]

    try:
        asyncio.run(run_test())
    finally:
        asyncio.run(engine.dispose())


def test_analysis_service_summary_event_limit_defaults_from_settings_but_explicit_value_wins(
    tmp_path: Path,
    monkeypatch,
) -> None:
    engine, session_maker = _setup_async_session(tmp_path)
    monkeypatch.setattr(
        "app.services.analysis_service.get_settings",
        lambda: SimpleNamespace(
            analysis_summary_event_limit=1,
            analysis_summary_candidate_pool_multiplier=4,
            web_source_metadata_timeout_seconds=3,
            web_source_metadata_cache_ttl_seconds=86400,
            web_source_metadata_failure_ttl_seconds=7200,
            web_source_metadata_max_bytes=1024 * 512,
        ),
    )

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
            base_time = datetime(2026, 3, 25, 12, 0, tzinfo=timezone.utc)
            for index in range(3):
                session.add(
                    NewsEvent(
                        id=f"summary-{index}",
                        scope="stock",
                        cache_variant="default",
                        ts_code="600519.SH",
                        symbol="600519",
                        title=f"摘要事件 {index}",
                        summary="摘要",
                        published_at=base_time - timedelta(minutes=index),
                        url=f"https://example.com/summary-{index}",
                        publisher="测试源",
                        source="eastmoney_stock",
                        fetched_at=base_time - timedelta(minutes=index),
                    )
                )
                session.add(
                    AnalysisEventLink(
                        event_id=f"summary-{index}",
                        ts_code="600519.SH",
                        correlation_score=0.8 - index * 0.1,
                        created_at=base_time - timedelta(minutes=index),
                    )
                )
            session.add(
                AnalysisReport(
                    ts_code="600519.SH",
                    status="ready",
                    summary="测试报告",
                    risk_points=[],
                    factor_breakdown=[],
                    generated_at=base_time,
                )
            )
            await session.commit()

            default_result = await get_stock_analysis_summary(session, "600519.SH")
            explicit_result = await get_stock_analysis_summary(
                session,
                "600519.SH",
                event_limit=2,
            )

            assert default_result["event_count"] == 1
            assert explicit_result["event_count"] == 2

    try:
        asyncio.run(run_test())
    finally:
        asyncio.run(engine.dispose())


def test_run_analysis_session_by_id_uses_balanced_event_selection_limit(
    tmp_path: Path,
    monkeypatch,
    caplog,
) -> None:
    engine, session_maker = _setup_async_session(tmp_path)
    captured = {"candidate_limit": None, "event_count": None}

    async def fake_load_recent_news_events(
        session,
        ts_code: str,
        *,
        topic,
        anchor_event_id,
        published_from,
        published_to,
        limit,
        candidate_limit=None,
    ):
        _ = (
            session,
            ts_code,
            topic,
            anchor_event_id,
            published_from,
            published_to,
            limit,
        )
        captured["candidate_limit"] = candidate_limit
        base_time = datetime(2026, 3, 25, 12, 0, tzinfo=timezone.utc)
        events: list[NewsEvent] = [
            NewsEvent(
                id="stock-anchor",
                scope="stock",
                cache_variant="default",
                ts_code="600519.SH",
                symbol="600519",
                title="锚点事件",
                summary="摘要",
                published_at=base_time,
                url="https://example.com/anchor",
                publisher="测试源",
                source="stock-source",
                macro_topic="commodity_supply",
                fetched_at=base_time,
            )
        ]
        for index in range(1, 12):
            events.append(
                NewsEvent(
                    id=f"stock-{index}",
                    scope="stock",
                    cache_variant="default",
                    ts_code="600519.SH",
                    symbol="600519",
                    title=f"个股事件 {index}",
                    summary="摘要",
                    published_at=base_time - timedelta(minutes=index),
                    url=f"https://example.com/stock-{index}",
                    publisher="测试源",
                    source="stock-source",
                    macro_topic="commodity_supply",
                    fetched_at=base_time - timedelta(minutes=index),
                )
            )
        for index in range(8):
            events.append(
                NewsEvent(
                    id=f"policy-{index}",
                    scope="policy",
                    cache_variant="policy_source",
                    title=f"政策事件 {index}",
                    summary="摘要",
                    published_at=base_time - timedelta(hours=1, minutes=index),
                    url=f"https://example.com/policy-{index}",
                    publisher="测试源",
                    source="policy-source",
                    macro_topic="commodity_supply",
                    fetched_at=base_time - timedelta(hours=1, minutes=index),
                )
            )
        for index in range(10):
            events.append(
                NewsEvent(
                    id=f"hot-{index}",
                    scope="hot",
                    cache_variant="global",
                    title=f"热点事件 {index}",
                    summary="摘要",
                    published_at=base_time - timedelta(hours=2, minutes=index),
                    url=f"https://example.com/hot-{index}",
                    publisher="测试源",
                    source="hot-source",
                    macro_topic="commodity_supply",
                    fetched_at=base_time - timedelta(hours=2, minutes=index),
                )
            )
        return events

    async def fake_generate_stock_analysis_report(
        *,
        ts_code: str,
        instrument_name: str | None,
        events,
        factor_weights,
        session,
        use_web_search: bool,
        on_delta,
    ):
        _ = (
            ts_code,
            instrument_name,
            factor_weights,
            session,
            use_web_search,
            on_delta,
        )
        captured["event_count"] = len(list(events))
        return AnalysisReportResult(
            status="ready",
            summary="测试报告",
            risk_points=[],
            factor_breakdown=[],
            generated_at=datetime(2026, 3, 25, 13, 0, tzinfo=timezone.utc),
            used_web_search=False,
            web_search_status="disabled",
            web_sources=[],
        )

    async def fake_publish(*args, **kwargs):
        _ = args, kwargs

    async def fake_cache(*args, **kwargs):
        _ = args, kwargs

    monkeypatch.setattr("app.services.analysis_service.SessionLocal", session_maker)
    monkeypatch.setattr(
        "app.services.analysis_service.load_recent_news_events",
        fake_load_recent_news_events,
    )
    monkeypatch.setattr(
        "app.services.analysis_service.generate_stock_analysis_report",
        fake_generate_stock_analysis_report,
    )
    monkeypatch.setattr("app.services.analysis_service.event_bus.publish", fake_publish)
    monkeypatch.setattr(
        "app.services.analysis_service.cache_fresh_report_id",
        fake_cache,
    )
    monkeypatch.setattr(
        "app.services.analysis_service.clear_cached_active_session_id",
        fake_cache,
    )

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
                AnalysisGenerationSession(
                    id="session-1",
                    analysis_key="analysis-key",
                    ts_code="600519.SH",
                    topic="commodity_supply",
                    anchor_event_id="stock-anchor",
                    status="queued",
                )
            )
            session.add_all(
                [
                    StockDailySnapshot(
                        ts_code="600519.SH",
                        trade_date=datetime(2026, 3, 25, tzinfo=timezone.utc).date(),
                        close=Decimal("1500.00"),
                        vol=Decimal("1000"),
                    ),
                    StockDailySnapshot(
                        ts_code="600519.SH",
                        trade_date=datetime(2026, 3, 26, tzinfo=timezone.utc).date(),
                        close=Decimal("1510.00"),
                        vol=Decimal("1200"),
                    ),
                ]
            )
            await session.commit()

        original_disabled = analysis_service_module.LOGGER.disabled
        original_propagate = analysis_service_module.LOGGER.propagate
        analysis_service_module.LOGGER.disabled = True
        analysis_service_module.LOGGER.propagate = False
        try:
            with caplog.at_level(logging.INFO, logger="app.services.analysis_service"):
                await run_analysis_session_by_id("session-1")
        finally:
            analysis_service_module.LOGGER.disabled = original_disabled
            analysis_service_module.LOGGER.propagate = original_propagate

        async with session_maker() as verify_session:
            persisted_report = (
                await verify_session.execute(
                    select(AnalysisReport).where(AnalysisReport.ts_code == "600519.SH")
                )
            ).scalar_one()

            assert persisted_report.summary == "测试报告"

        assert captured["candidate_limit"] == 120
        assert captured["event_count"] == 30
        assert "event=analysis_session_started session_id=session-1" in caplog.text
        assert "event=analysis_session_completed session_id=session-1" in caplog.text

    try:
        asyncio.run(run_test())
    finally:
        asyncio.run(engine.dispose())
