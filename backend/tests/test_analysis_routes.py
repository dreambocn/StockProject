from pathlib import Path
import asyncio
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.session import get_db_session
from app.main import app
from app.models.analysis_event_link import AnalysisEventLink
from app.models.analysis_generation_session import AnalysisGenerationSession
from app.models.analysis_report import AnalysisReport
from app.models.news_event import NewsEvent
from app.models.stock_kline_bar import StockKlineBar
from app.models.stock_instrument import StockInstrument


def _prepare_analysis_client(tmp_path: Path):
    db_path = tmp_path / "analysis-test.db"
    db_url = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    engine = create_async_engine(db_url)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    async def _create_tables() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(_create_tables())

    async def override_session():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_session
    client = TestClient(app)
    return client, engine


def _cleanup_analysis_client(engine):
    app.dependency_overrides.clear()
    asyncio.run(engine.dispose())


def test_analysis_summary_route_returns_pending_when_empty(tmp_path: Path) -> None:
    client, engine = _prepare_analysis_client(tmp_path)
    try:
        response = client.get("/api/analysis/stocks/600519.SH/summary")
    finally:
        _cleanup_analysis_client(engine)

    assert response.status_code == 200
    payload = response.json()
    assert payload["ts_code"] == "600519.SH"
    assert isinstance(payload.get("events"), list)
    assert payload["events"] == []
    assert payload["report"] is None
    assert payload["status"] in {"pending", "partial"}


def test_analysis_summary_route_supports_event_id_and_returns_anchor_fields(
    tmp_path: Path,
) -> None:
    client, engine = _prepare_analysis_client(tmp_path)
    try:
        async def _seed() -> None:
            override_session = app.dependency_overrides[get_db_session]
            async for session in override_session():
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
                        url="https://finance.example.com/h/1",
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
                        correlation_score=0.9,
                        confidence="high",
                        link_status="linked",
                    )
                )
                session.add(
                    AnalysisReport(
                        ts_code="600519.SH",
                        status="ready",
                        summary="测试报告",
                        risk_points=["风险提示"],
                        factor_breakdown=[],
                        topic="commodity_supply",
                        anchor_event_id="evt-hot-1",
                        anchor_event_title="国际油价高位震荡",
                        structured_sources=[{"provider": "akshare", "count": 1}],
                        generated_at=datetime(2026, 3, 3, 10, 10, tzinfo=timezone.utc),
                    )
                )
                await session.commit()
                break

        asyncio.run(_seed())
        response = client.get(
            "/api/analysis/stocks/600519.SH/summary",
            params={"topic": "commodity_supply", "event_id": "evt-hot-1"},
        )
    finally:
        _cleanup_analysis_client(engine)

    assert response.status_code == 200
    payload = response.json()
    assert payload["topic"] == "commodity_supply"
    assert payload["report"]["anchor_event_id"] == "evt-hot-1"
    assert payload["report"]["anchor_event_title"] == "国际油价高位震荡"
    assert payload["report"]["structured_sources"] == [{"provider": "akshare", "count": 1}]


def test_analysis_summary_route_backfills_latest_snapshot_from_daily_kline(
    tmp_path: Path,
) -> None:
    client, engine = _prepare_analysis_client(tmp_path)
    try:
        async def _seed() -> None:
            override_session = app.dependency_overrides[get_db_session]
            async for session in override_session():
                session.add(
                    StockInstrument(
                        ts_code='000001.SZ',
                        symbol='000001',
                        name='平安银行',
                        fullname='平安银行股份有限公司',
                        list_status='L',
                    )
                )
                session.add(
                    StockKlineBar(
                        ts_code='000001.SZ',
                        period='daily',
                        trade_date=datetime(2026, 3, 31, tzinfo=timezone.utc).date(),
                        end_date=None,
                        open=11.00,
                        high=11.18,
                        low=10.96,
                        close=11.08,
                        pre_close=10.99,
                        change=0.09,
                        pct_chg=0.8189,
                        vol=100000,
                        amount=200000,
                    )
                )
                await session.commit()
                break

        asyncio.run(_seed())
        response = client.get('/api/analysis/stocks/000001.SZ/summary')
    finally:
        _cleanup_analysis_client(engine)

    assert response.status_code == 200
    payload = response.json()
    assert payload['latest_snapshot']['trade_date'] == '2026-03-31'
    assert payload['latest_snapshot']['close'] == 11.08
    assert payload['latest_snapshot']['pct_chg'] == 0.8189


def test_analysis_summary_route_prefers_full_report_evidence_snapshot(
    tmp_path: Path,
) -> None:
    client, engine = _prepare_analysis_client(tmp_path)
    try:
        async def _seed() -> None:
            override_session = app.dependency_overrides[get_db_session]
            async for session in override_session():
                session.add(
                    StockInstrument(
                        ts_code='000001.SZ',
                        symbol='000001',
                        name='平安银行',
                        fullname='平安银行股份有限公司',
                        list_status='L',
                    )
                )
                session.add(
                    AnalysisReport(
                        id='report-full-evidence',
                        ts_code='000001.SZ',
                        status='ready',
                        summary='完整证据报告',
                        risk_points=[],
                        factor_breakdown=[],
                        structured_sources=[
                            {'provider': 'akshare', 'count': 23},
                            {'provider': 'tushare', 'count': 7},
                        ],
                        evidence_event_count=25,
                        evidence_events=[
                            {
                                'event_id': f'evt-{index}',
                                'scope': 'policy' if index % 5 == 0 else 'hot',
                                'title': f'证据事件 {index}',
                                'published_at': '2026-03-23T08:00:00Z',
                                'source': 'policy_document' if index % 5 == 0 else 'eastmoney_global',
                                'macro_topic': 'regulation_policy' if index % 5 == 0 else 'industry',
                                'event_type': 'policy' if index % 5 == 0 else 'news',
                                'event_tags': ['政策'] if index % 5 == 0 else ['行业'],
                                'sentiment_label': 'positive',
                                'sentiment_score': 0.7,
                                'anchor_trade_date': '2026-03-24',
                                'window_return_pct': 1.5 + index,
                                'window_volatility': 0.8 + index,
                                'abnormal_volume_ratio': 1.1 + index,
                                'correlation_score': 0.85 if index % 4 == 0 else 0.45,
                                'confidence': 'high',
                                'link_status': 'linked',
                            }
                            for index in range(25)
                        ],
                        generated_at=datetime(2026, 3, 24, 10, 0, tzinfo=timezone.utc),
                    )
                )
                await session.commit()
                break

        asyncio.run(_seed())
        response = client.get('/api/analysis/stocks/000001.SZ/summary')
    finally:
        _cleanup_analysis_client(engine)

    assert response.status_code == 200
    payload = response.json()
    assert payload['event_count'] == 25
    assert len(payload['events']) == 25
    assert payload['events'][0]['event_id'] == 'evt-0'
    assert payload['report']['evidence_event_count'] == 25
    assert len(payload['report']['evidence_events']) == 25


def test_analysis_report_evidence_route_returns_report_snapshot(
    tmp_path: Path,
) -> None:
    client, engine = _prepare_analysis_client(tmp_path)
    try:
        async def _seed() -> None:
            override_session = app.dependency_overrides[get_db_session]
            async for session in override_session():
                session.add(
                    AnalysisReport(
                        id='report-evidence-1',
                        ts_code='600519.SH',
                        status='ready',
                        summary='测试报告',
                        risk_points=[],
                        factor_breakdown=[],
                        evidence_event_count=2,
                        evidence_events=[
                            {
                                'event_id': 'evt-policy-1',
                                'scope': 'policy',
                                'title': '政策事件',
                                'published_at': '2026-03-23T08:00:00Z',
                                'source': 'policy_document',
                                'macro_topic': 'regulation_policy',
                                'event_type': 'policy',
                                'event_tags': ['政策'],
                                'sentiment_label': 'positive',
                                'sentiment_score': 0.9,
                                'anchor_trade_date': '2026-03-24',
                                'window_return_pct': 2.5,
                                'window_volatility': 1.2,
                                'abnormal_volume_ratio': 1.9,
                                'correlation_score': 0.91,
                                'confidence': 'high',
                                'link_status': 'linked',
                            },
                            {
                                'event_id': 'evt-news-1',
                                'scope': 'hot',
                                'title': '热点事件',
                                'published_at': '2026-03-23T09:00:00Z',
                                'source': 'eastmoney_global',
                                'macro_topic': 'industry',
                                'event_type': 'news',
                                'event_tags': ['行业'],
                                'sentiment_label': 'neutral',
                                'sentiment_score': 0.1,
                                'anchor_trade_date': '2026-03-24',
                                'window_return_pct': 1.3,
                                'window_volatility': 0.7,
                                'abnormal_volume_ratio': 1.4,
                                'correlation_score': 0.72,
                                'confidence': 'medium',
                                'link_status': 'linked',
                            },
                        ],
                        generated_at=datetime(2026, 3, 24, 10, 0, tzinfo=timezone.utc),
                    )
                )
                await session.commit()
                break

        asyncio.run(_seed())
        response = client.get('/api/analysis/reports/report-evidence-1/evidence')
    finally:
        _cleanup_analysis_client(engine)

    assert response.status_code == 200
    payload = response.json()
    assert payload['report_id'] == 'report-evidence-1'
    assert payload['ts_code'] == '600519.SH'
    assert payload['event_count'] == 2
    assert [item['event_id'] for item in payload['events']] == ['evt-policy-1', 'evt-news-1']


def test_analysis_report_evidence_route_falls_back_when_snapshot_missing(
    tmp_path: Path,
) -> None:
    client, engine = _prepare_analysis_client(tmp_path)
    try:
        async def _seed() -> None:
            override_session = app.dependency_overrides[get_db_session]
            async for session in override_session():
                session.add(
                    NewsEvent(
                        id='evt-fallback-1',
                        scope='policy',
                        cache_variant='policy_source',
                        title='存量政策事件',
                        summary='政策摘要',
                        published_at=datetime(2026, 3, 22, 10, 0, tzinfo=timezone.utc),
                        url='https://example.com/policy',
                        publisher='政策源',
                        source='policy_document',
                        macro_topic='regulation_policy',
                        event_type='policy',
                        fetched_at=datetime(2026, 3, 22, 10, 5, tzinfo=timezone.utc),
                    )
                )
                session.add(
                    AnalysisEventLink(
                        event_id='evt-fallback-1',
                        ts_code='600519.SH',
                        anchor_trade_date=datetime(2026, 3, 24, tzinfo=timezone.utc).date(),
                        window_return_pct=1.8,
                        window_volatility=0.9,
                        abnormal_volume_ratio=1.5,
                        correlation_score=0.88,
                        confidence='high',
                        link_status='linked',
                    )
                )
                session.add(
                    AnalysisReport(
                        id='report-fallback-1',
                        ts_code='600519.SH',
                        status='ready',
                        summary='旧报告',
                        risk_points=[],
                        factor_breakdown=[],
                        evidence_event_count=None,
                        evidence_events=None,
                        generated_at=datetime(2026, 3, 24, 10, 0, tzinfo=timezone.utc),
                    )
                )
                await session.commit()
                break

        asyncio.run(_seed())
        response = client.get('/api/analysis/reports/report-fallback-1/evidence')
    finally:
        _cleanup_analysis_client(engine)

    assert response.status_code == 200
    payload = response.json()
    assert payload['report_id'] == 'report-fallback-1'
    assert payload['event_count'] == 1
    assert payload['events'][0]['event_id'] == 'evt-fallback-1'


def test_analysis_reports_route_backfills_web_source_metadata_on_read(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, engine = _prepare_analysis_client(tmp_path)

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

    try:
        async def _seed() -> None:
            override_session = app.dependency_overrides[get_db_session]
            async for session in override_session():
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
                break

        asyncio.run(_seed())
        response = client.get("/api/analysis/stocks/600519.SH/reports")
    finally:
        _cleanup_analysis_client(engine)

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"][0]["web_sources"][0]["source"] == "Reuters"
    assert payload["items"][0]["web_sources"][0]["published_at"] == "2026-03-24T09:30:00+00:00"
    assert payload["items"][0]["web_sources"][0]["domain"] == "finance.example.com"
    assert payload["items"][0]["web_sources"][0]["metadata_status"] == "enriched"


def test_analysis_reports_route_forces_domain_source_when_backfill_unavailable(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, engine = _prepare_analysis_client(tmp_path)

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

    try:
        async def _seed() -> None:
            override_session = app.dependency_overrides[get_db_session]
            async for session in override_session():
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
                break

        asyncio.run(_seed())
        response = client.get("/api/analysis/stocks/600519.SH/reports")
    finally:
        _cleanup_analysis_client(engine)

    assert response.status_code == 200
    payload = response.json()
    web_source = payload["items"][0]["web_sources"][0]
    assert web_source["metadata_status"] == "unavailable"
    assert web_source["source"] == "finance.example.com"
    assert web_source["published_at"] is None


def test_analysis_reports_route_respects_three_three_ten_backfill_budget(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, engine = _prepare_analysis_client(tmp_path)
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

    try:
        async def _seed() -> None:
            override_session = app.dependency_overrides[get_db_session]
            async for session in override_session():
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
                break

        asyncio.run(_seed())
        response = client.get("/api/analysis/stocks/600519.SH/reports")
    finally:
        _cleanup_analysis_client(engine)

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["items"]) == 4
    assert len(called_sizes) == 3
    assert all(size <= 3 for size in called_sizes)
    assert sum(called_sizes) <= 10


def test_analysis_reports_route_skips_reenrichment_for_domain_inferred_fallback_ready_source(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, engine = _prepare_analysis_client(tmp_path)
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

    try:
        async def _seed() -> None:
            override_session = app.dependency_overrides[get_db_session]
            async for session in override_session():
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
                                "metadata_status": "domain_inferred",
                                "snippet": "市场继续关注供给端扰动。",
                            }
                        ],
                        generated_at=datetime(2026, 3, 24, 10, 0, tzinfo=timezone.utc),
                    )
                )
                await session.commit()
                break

        asyncio.run(_seed())
        first = client.get("/api/analysis/stocks/600519.SH/reports")
        second = client.get("/api/analysis/stocks/600519.SH/reports")
    finally:
        _cleanup_analysis_client(engine)

    assert first.status_code == 200
    assert second.status_code == 200
    assert called_times["count"] == 0
