import asyncio
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.session import get_db_session
from app.main import app
import app.api.routes.news as news_routes
import app.api.routes.stocks as stocks_routes
from app.models.news_fetch_batch import NewsFetchBatch
from app.models.news_event import NewsEvent
from app.models.stock_instrument import StockInstrument
from app.schemas.news import (
    CandidateEvidenceItemResponse,
    CandidateEvidenceSourceBreakdownResponse,
    CandidateEvidenceSummaryResponse,
)


class FakeRedisClient:
    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self._store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> bool:
        _ = ex
        self._store[key] = value
        return True

    async def delete(self, key: str) -> int:
        if key in self._store:
            del self._store[key]
            return 1
        return 0


@pytest.fixture
def news_client(tmp_path: Path) -> TestClient:
    db_path = tmp_path / "news-test.db"
    db_url = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    engine = create_async_engine(db_url)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    async def _create_tables() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    async def _seed_data() -> None:
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
                        ts_code="600547.SH",
                        symbol="600547",
                        name="山东黄金",
                        fullname="山东黄金矿业股份有限公司",
                        area="山东",
                        industry="黄金",
                        market="主板",
                        exchange="SSE",
                        list_status="L",
                        list_date=date(2003, 8, 28),
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
                        ts_code="600900.SH",
                        symbol="600900",
                        name="长江电力",
                        fullname="中国长江电力股份有限公司",
                        area="北京",
                        industry="电力",
                        market="主板",
                        exchange="SSE",
                        list_status="L",
                        list_date=date(2003, 11, 18),
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
                    StockInstrument(
                        ts_code="601318.SH",
                        symbol="601318",
                        name="中国平安",
                        fullname="中国平安保险(集团)股份有限公司",
                        area="广东",
                        industry="保险",
                        market="主板",
                        exchange="SSE",
                        list_status="L",
                        list_date=date(2007, 3, 1),
                        delist_date=None,
                        is_hs="N",
                    ),
                    NewsEvent(
                        scope="stock",
                        cache_variant="with_announcements",
                        ts_code="600029.SH",
                        symbol="600029",
                        title="南方航空发布运力恢复公告",
                        summary="客运恢复超预期",
                        published_at=datetime(2026, 3, 3, 9, 0, tzinfo=UTC),
                        url="https://finance.example.com/s/1",
                        publisher="证券时报",
                        source="eastmoney_stock",
                        macro_topic=None,
                        fetched_at=datetime(2026, 3, 3, 9, 5, tzinfo=UTC),
                    ),
                    NewsEvent(
                        scope="hot",
                        cache_variant="global",
                        ts_code=None,
                        symbol=None,
                        title="国际油价高位震荡",
                        summary="原油供需偏紧",
                        published_at=datetime(2026, 3, 3, 10, 0, tzinfo=UTC),
                        url="https://finance.example.com/h/1",
                        publisher=None,
                        source="eastmoney_global",
                        macro_topic="commodity_supply",
                        fetched_at=datetime(2026, 3, 3, 10, 5, tzinfo=UTC),
                    ),
                    NewsEvent(
                        scope="hot",
                        cache_variant="global",
                        ts_code=None,
                        symbol=None,
                        title="美联储官员讲话",
                        summary="市场关注降息路径",
                        published_at=datetime(2026, 3, 2, 20, 0, tzinfo=UTC),
                        url="https://finance.example.com/h/2",
                        publisher=None,
                        source="eastmoney_global",
                        macro_topic="monetary_policy",
                        fetched_at=datetime(2026, 3, 2, 20, 5, tzinfo=UTC),
                    ),
                ]
            )
            await session.commit()

    import asyncio

    fake_redis = FakeRedisClient()
    original_get_redis_client = news_routes.get_redis_client
    original_stock_get_redis_client = stocks_routes.get_redis_client
    original_fetch_major_news = news_routes.TushareGateway.fetch_major_news
    original_get_candidate_evidence_snapshots = (
        news_routes.attach_dynamic_a_share_candidates.__globals__.get(
            "get_candidate_evidence_snapshots"
        )
    )

    asyncio.run(_create_tables())
    asyncio.run(_seed_data())

    async def _override_session():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_db_session] = _override_session
    news_routes.get_redis_client = lambda: fake_redis
    stocks_routes.get_redis_client = lambda: fake_redis

    async def _fake_fetch_major_news(self) -> list[dict[str, object]]:
        return []

    async def _fake_candidate_evidence_snapshots(*args, **kwargs) -> dict[str, object]:
        _ = args
        _ = kwargs
        return {}

    news_routes.TushareGateway.fetch_major_news = _fake_fetch_major_news
    news_routes.attach_dynamic_a_share_candidates.__globals__[
        "get_candidate_evidence_snapshots"
    ] = _fake_candidate_evidence_snapshots

    with TestClient(app) as client:
        client.session_maker = session_maker
        client.fake_redis = fake_redis
        yield client

    app.dependency_overrides.pop(get_db_session, None)
    news_routes.get_redis_client = original_get_redis_client
    stocks_routes.get_redis_client = original_stock_get_redis_client
    news_routes.TushareGateway.fetch_major_news = original_fetch_major_news
    if original_get_candidate_evidence_snapshots is not None:
        news_routes.attach_dynamic_a_share_candidates.__globals__[
            "get_candidate_evidence_snapshots"
        ] = original_get_candidate_evidence_snapshots
    asyncio.run(engine.dispose())


def _append_news_events(news_client: TestClient, rows: list[NewsEvent]) -> None:
    async def _run() -> None:
        async with news_client.session_maker() as session:
            session.add_all(rows)
            await session.commit()

    asyncio.run(_run())


def _load_news_fetch_batches(news_client: TestClient, *, scope: str) -> list[NewsFetchBatch]:
    async def _run() -> list[NewsFetchBatch]:
        async with news_client.session_maker() as session:
            rows = (
                await session.execute(
                    select(NewsFetchBatch)
                    .where(NewsFetchBatch.scope == scope)
                    .order_by(NewsFetchBatch.created_at.asc())
                )
            ).scalars().all()
            return list(rows)

    return asyncio.run(_run())


def test_hot_news_route_calls_gateway_once_and_returns_remote_rows(
    news_client: TestClient, monkeypatch
) -> None:
    called = {"count": 0}

    async def fake_fetch_hot_news() -> list[dict[str, object]]:
        called["count"] += 1
        return []

    monkeypatch.setattr("app.api.routes.news.fetch_hot_news", fake_fetch_hot_news)

    response = news_client.get("/api/news/hot")

    assert response.status_code == 200
    assert called["count"] == 1
    assert len(response.json()) > 0


def test_hot_news_response_contains_normalized_fields(
    news_client: TestClient, monkeypatch
) -> None:
    async def fake_fetch_hot_news() -> list[dict[str, object]]:
        return [
            {
                "标题": "中东局势升级",
                "摘要": "避险情绪升温",
                "发布时间": "2026-03-03 09:00:00",
                "链接": "https://finance.example.com/a/2",
            }
        ]

    monkeypatch.setattr("app.api.routes.news.fetch_hot_news", fake_fetch_hot_news)

    response = news_client.get("/api/news/hot")

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["title"] == "中东局势升级"
    assert payload[0]["summary"] == "避险情绪升温"
    assert payload[0]["source"] == "eastmoney_global"
    assert payload[0]["macro_topic"] == "geopolitical_conflict"


def test_hot_news_response_contains_event_cluster_and_provider_fields(
    news_client: TestClient, monkeypatch
) -> None:
    async def fake_fetch_hot_news() -> list[dict[str, object]]:
        return [
            {
                "标题": "中东局势升级",
                "摘要": "避险情绪升温",
                "发布时间": "2026-03-03 09:00:00",
                "链接": "https://finance.example.com/a/2",
            }
        ]

    monkeypatch.setattr("app.api.routes.news.fetch_hot_news", fake_fetch_hot_news)
    async def fake_fetch_major_news(self) -> list[dict[str, object]]:
        return []

    monkeypatch.setattr(
        "app.api.routes.news.TushareGateway.fetch_major_news",
        fake_fetch_major_news,
    )

    response = news_client.get("/api/news/hot")

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["event_id"]
    assert payload[0]["cluster_key"]
    assert payload[0]["providers"] == ["akshare"]
    assert payload[0]["source_coverage"] == "AK"


def test_hot_news_supports_macro_topic_filter(
    news_client: TestClient, monkeypatch
) -> None:
    async def fake_fetch_hot_news() -> list[dict[str, object]]:
        return [
            {
                "标题": "中东局势升级引发避险情绪",
                "摘要": "全球市场关注冲突风险",
                "发布时间": "2026-03-03 09:00:00",
                "链接": "https://finance.example.com/a/2",
            },
            {
                "标题": "美联储降息预期升温",
                "摘要": "市场关注后续利率路径",
                "发布时间": "2026-03-03 10:00:00",
                "链接": "https://finance.example.com/a/3",
            },
        ]

    monkeypatch.setattr("app.api.routes.news.fetch_hot_news", fake_fetch_hot_news)

    response = news_client.get(
        "/api/news/hot",
        params={"topic": "commodity_supply"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 0


def test_hot_news_upstream_error_falls_back_to_db(
    news_client: TestClient, monkeypatch
) -> None:
    async def fake_fetch_hot_news() -> list[dict[str, object]]:
        raise RuntimeError("upstream down")

    monkeypatch.setattr("app.api.routes.news.fetch_hot_news", fake_fetch_hot_news)

    response = news_client.get("/api/news/hot")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) > 0


def test_hot_news_logs_warning_when_akshare_upstream_fails(
    news_client: TestClient, monkeypatch
) -> None:
    warning_calls: list[tuple[str, tuple[object, ...]]] = []

    async def fake_fetch_hot_news() -> list[dict[str, object]]:
        raise RuntimeError("akshare upstream down")

    def fake_warning(message: str, *args: object, **kwargs: object) -> None:
        _ = kwargs
        warning_calls.append((message, args))

    monkeypatch.setattr("app.api.routes.news.fetch_hot_news", fake_fetch_hot_news)
    monkeypatch.setattr("app.api.routes.news.logger.warning", fake_warning)

    response = news_client.get("/api/news/hot")

    assert response.status_code == 200
    assert any(
        call_args[:2] == ("akshare", "RuntimeError")
        for _message, call_args in warning_calls
    )


def test_hot_news_logs_warning_when_tushare_upstream_fails(
    news_client: TestClient, monkeypatch
) -> None:
    warning_calls: list[tuple[str, tuple[object, ...]]] = []

    async def fake_fetch_hot_news() -> list[dict[str, object]]:
        return []

    async def fake_fetch_major_news(_self) -> list[dict[str, object]]:
        raise RuntimeError("tushare upstream down")

    def fake_warning(message: str, *args: object, **kwargs: object) -> None:
        _ = kwargs
        warning_calls.append((message, args))

    monkeypatch.setattr("app.api.routes.news.fetch_hot_news", fake_fetch_hot_news)
    monkeypatch.setattr(
        "app.api.routes.news.TushareGateway.fetch_major_news",
        fake_fetch_major_news,
    )
    monkeypatch.setattr(
        "app.api.routes.news.get_settings",
        lambda: SimpleNamespace(
            tushare_token="test-token",
            hot_news_cache_ttl_seconds=3600,
        ),
    )
    monkeypatch.setattr("app.api.routes.news.logger.warning", fake_warning)

    response = news_client.get("/api/news/hot")

    assert response.status_code == 200
    assert any(
        call_args[:2] == ("tushare", "RuntimeError")
        for _message, call_args in warning_calls
    )


def test_hot_news_uses_cache_and_persists_to_db(
    news_client: TestClient, monkeypatch
) -> None:
    called = {"count": 0}

    async def fake_fetch_hot_news() -> list[dict[str, object]]:
        called["count"] += 1
        return [
            {
                "标题": "中东局势升级",
                "摘要": "避险情绪升温",
                "发布时间": "2026-03-03 09:00:00",
                "链接": "https://finance.example.com/a/2",
            }
        ]

    monkeypatch.setattr("app.api.routes.news.fetch_hot_news", fake_fetch_hot_news)

    first = news_client.get("/api/news/hot")
    second = news_client.get("/api/news/hot")

    assert first.status_code == 200
    assert second.status_code == 200
    assert called["count"] == 1
    assert second.json()[0]["title"] == "中东局势升级"


def test_hot_news_route_persists_fetch_batch_and_version_key(
    news_client: TestClient,
    monkeypatch,
) -> None:
    async def fake_fetch_hot_news() -> list[dict[str, object]]:
        return [
            {
                "标题": "中东局势升级",
                "摘要": "避险情绪升温",
                "发布时间": "2026-03-03 09:00:00",
                "链接": "https://finance.example.com/a/2",
            }
        ]

    monkeypatch.setattr("app.api.routes.news.fetch_hot_news", fake_fetch_hot_news)

    response = news_client.get("/api/news/hot")

    assert response.status_code == 200
    batches = _load_news_fetch_batches(news_client, scope="hot")
    assert len(batches) == 1
    assert batches[0].status == "success"
    assert batches[0].trigger_source == "api.news.hot"
    assert batches[0].row_count_persisted == 1
    assert "news:hot:global:version" in news_client.fake_redis._store


def test_impact_map_endpoint_returns_profiles(news_client: TestClient) -> None:
    response = news_client.get("/api/news/impact-map")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) > 0
    assert payload[0]["topic"]
    assert isinstance(payload[0]["beneficiary_sectors"], list)


def test_impact_map_endpoint_supports_topic_filter(news_client: TestClient) -> None:
    response = news_client.get(
        "/api/news/impact-map",
        params={"topic": "commodity_supply"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["topic"] == "commodity_supply"


def test_impact_map_returns_dynamic_a_share_candidates(
    news_client: TestClient,
) -> None:
    response = news_client.get(
        "/api/news/impact-map",
        params={"topic": "commodity_supply"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    candidates = payload[0]["a_share_candidates"]
    assert len(candidates) > 0
    assert any(item["name"] == "中国海油" for item in candidates)
    assert any(item["name"] == "山东黄金" for item in candidates)


def test_impact_map_returns_anchor_event_and_scored_candidates(
    news_client: TestClient,
) -> None:
    response = news_client.get(
        "/api/news/impact-map",
        params={"topic": "commodity_supply"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["anchor_event"]["event_id"]
    assert payload[0]["anchor_event"]["title"] == "国际油价高位震荡"
    assert payload[0]["anchor_event"]["source_coverage"] in {"AK", "TS", "AK+TS"}
    first_candidate = payload[0]["a_share_candidates"][0]
    assert first_candidate["relevance_score"] >= 35
    assert first_candidate["source_hit_count"] >= 1
    assert first_candidate["match_reasons"]
    assert isinstance(first_candidate["evidence_summary"], str)


def test_impact_map_returns_candidate_enhancement_fields(
    news_client: TestClient,
    monkeypatch,
) -> None:
    async def fake_candidate_snapshots(*args, **kwargs) -> dict[str, CandidateEvidenceSummaryResponse]:
        _ = args
        _ = kwargs
        return {
            "600938.SH": CandidateEvidenceSummaryResponse(
                ts_code="600938.SH",
                hot_search_count=1,
                research_report_count=1,
                latest_published_at=datetime(2026, 3, 23, 8, 0, tzinfo=UTC),
                source_breakdown=[
                    CandidateEvidenceSourceBreakdownResponse(
                        source="hot_search",
                        count=1,
                    ),
                    CandidateEvidenceSourceBreakdownResponse(
                        source="research_report",
                        count=1,
                    ),
                ],
                evidence_items=[
                    CandidateEvidenceItemResponse(
                        ts_code="600938.SH",
                        symbol="600938",
                        name="中国海油",
                        evidence_kind="hot_search",
                        title="中国海油进入百度热搜",
                        summary="百度热搜排名第 1 位",
                        published_at=datetime(2026, 3, 23, 8, 0, tzinfo=UTC),
                        url=None,
                        source="baidu_hot_search",
                    ),
                    CandidateEvidenceItemResponse(
                        ts_code="600938.SH",
                        symbol="600938",
                        name="中国海油",
                        evidence_kind="research_report",
                        title="油价上行驱动盈利改善",
                        summary="机构发布研报",
                        published_at=datetime(2026, 3, 22, 8, 0, tzinfo=UTC),
                        url=None,
                        source="eastmoney_research_report",
                    ),
                    CandidateEvidenceItemResponse(
                        ts_code="600938.SH",
                        symbol="600938",
                        name="中国海油",
                        evidence_kind="research_report",
                        title="现金流表现稳健",
                        summary="机构维持买入",
                        published_at=datetime(2026, 3, 21, 8, 0, tzinfo=UTC),
                        url=None,
                        source="eastmoney_research_report",
                    ),
                ],
            )
        }

    monkeypatch.setattr(
        "app.services.news_mapper_service.get_candidate_evidence_snapshots",
        fake_candidate_snapshots,
    )

    response = news_client.get(
        "/api/news/impact-map",
        params={"topic": "commodity_supply", "candidate_evidence_limit": 2},
    )

    assert response.status_code == 200
    payload = response.json()
    first_candidate = payload[0]["a_share_candidates"][0]
    assert first_candidate["source_breakdown"] == [
        {"source": "hot_search", "count": 1},
        {"source": "research_report", "count": 1},
    ]
    assert first_candidate["freshness_score"] > 0
    assert first_candidate["candidate_confidence"] in {"高", "中", "低"}
    assert len(first_candidate["evidence_items"]) == 2


def test_impact_map_only_requests_evidence_for_candidate_pool(
    news_client: TestClient,
    monkeypatch,
) -> None:
    captured_ts_codes: list[str] = []

    async def fake_candidate_snapshots(*args, **kwargs) -> dict[str, CandidateEvidenceSummaryResponse]:
        _ = args
        captured_ts_codes.extend(kwargs["ts_codes"])
        return {}

    monkeypatch.setattr(
        "app.services.news_mapper_service.get_candidate_evidence_snapshots",
        fake_candidate_snapshots,
    )

    response = news_client.get(
        "/api/news/impact-map",
        params={"topic": "commodity_supply", "candidate_limit": 1},
    )

    assert response.status_code == 200
    assert sorted(captured_ts_codes) == ["600547.SH", "600938.SH"]


def test_impact_map_enhanced_evidence_promotes_candidate_order(
    news_client: TestClient,
    monkeypatch,
) -> None:
    async def fake_candidate_snapshots(*args, **kwargs) -> dict[str, CandidateEvidenceSummaryResponse]:
        _ = args
        _ = kwargs
        return {
            "600547.SH": CandidateEvidenceSummaryResponse(
                ts_code="600547.SH",
                hot_search_count=1,
                research_report_count=1,
                latest_published_at=datetime(2026, 3, 23, 9, 0, tzinfo=UTC),
                source_breakdown=[
                    CandidateEvidenceSourceBreakdownResponse(
                        source="hot_search",
                        count=1,
                    ),
                    CandidateEvidenceSourceBreakdownResponse(
                        source="research_report",
                        count=1,
                    ),
                ],
                evidence_items=[
                    CandidateEvidenceItemResponse(
                        ts_code="600547.SH",
                        symbol="600547",
                        name="山东黄金",
                        evidence_kind="hot_search",
                        title="山东黄金进入百度热搜",
                        summary="百度热搜排名第 3 位",
                        published_at=datetime(2026, 3, 23, 9, 0, tzinfo=UTC),
                        url=None,
                        source="baidu_hot_search",
                    )
                ],
            )
        }

    monkeypatch.setattr(
        "app.services.news_mapper_service.get_candidate_evidence_snapshots",
        fake_candidate_snapshots,
    )

    response = news_client.get(
        "/api/news/impact-map",
        params={"topic": "commodity_supply"},
    )

    assert response.status_code == 200
    payload = response.json()
    candidates = payload[0]["a_share_candidates"]
    assert candidates[0]["name"] == "山东黄金"
    assert candidates[0]["relevance_score"] > candidates[1]["relevance_score"]


def test_impact_map_keeps_base_candidates_when_enhancement_snapshot_fails(
    news_client: TestClient,
    monkeypatch,
) -> None:
    async def fake_candidate_snapshots_failed(*args, **kwargs) -> dict[str, CandidateEvidenceSummaryResponse]:
        _ = args
        _ = kwargs
        raise RuntimeError("候选增强快照服务异常")

    monkeypatch.setattr(
        "app.services.news_mapper_service.get_candidate_evidence_snapshots",
        fake_candidate_snapshots_failed,
    )

    response = news_client.get(
        "/api/news/impact-map",
        params={"topic": "commodity_supply"},
    )

    assert response.status_code == 200
    payload = response.json()
    candidates = payload[0]["a_share_candidates"]
    # 增强失败时仍需保留基础候选链路，不能被路由层整体清空。
    assert len(candidates) > 0
    assert any(item["name"] == "中国海油" for item in candidates)
    assert any(item["name"] == "山东黄金" for item in candidates)
    # 降级后增强字段应保持默认空态，接口结构不变。
    assert candidates[0]["source_breakdown"] == []
    assert candidates[0]["evidence_items"] == []


def test_impact_map_route_keeps_existing_candidates_when_attach_raises(
    news_client: TestClient,
    monkeypatch,
) -> None:
    warning_calls: list[tuple[str, tuple[object, ...]]] = []

    def fake_profiles(_topic: str) -> list[dict[str, object]]:
        return [
            {
                "topic": "commodity_supply",
                "affected_assets": ["原油"],
                "beneficiary_sectors": ["油气开采"],
                "pressure_sectors": ["航空运输"],
                "a_share_targets": ["中国海油"],
                "anchor_event": None,
                "a_share_candidates": [
                    {
                        "ts_code": "600938.SH",
                        "symbol": "600938",
                        "name": "中国海油",
                        "industry": "石油开采",
                        "relevance_score": 35,
                        "match_reasons": ["命中主题目标股"],
                        "evidence_summary": "命中主题目标股",
                        "source_hit_count": 1,
                        "source_breakdown": [],
                        "freshness_score": 0,
                        "candidate_confidence": "中",
                        "evidence_items": [],
                    }
                ],
            }
        ]

    async def fake_attach_dynamic_a_share_candidates(*args, **kwargs):
        _ = args, kwargs
        raise RuntimeError("dynamic attach failed")

    def fake_warning(message: str, *args: object, **kwargs: object) -> None:
        _ = kwargs
        warning_calls.append((message, args))

    monkeypatch.setattr("app.api.routes.news.list_macro_impact_profiles", fake_profiles)
    monkeypatch.setattr(
        "app.api.routes.news.attach_dynamic_a_share_candidates",
        fake_attach_dynamic_a_share_candidates,
    )
    monkeypatch.setattr("app.api.routes.news.logger.warning", fake_warning)

    response = news_client.get("/api/news/impact-map", params={"topic": "commodity_supply"})

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["a_share_candidates"][0]["name"] == "中国海油"
    assert any(
        call_args[:1] == ("RuntimeError",)
        for _message, call_args in warning_calls
    )


def test_news_events_endpoint_supports_ts_code_filter(news_client: TestClient) -> None:
    response = news_client.get(
        "/api/news/events",
        params={"ts_code": "600029.SH"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["scope"] == "stock"
    assert payload[0]["ts_code"] == "600029.SH"
    assert payload[0]["title"] == "南方航空发布运力恢复公告"


def test_news_events_endpoint_supports_topic_and_time_filter(
    news_client: TestClient,
) -> None:
    response = news_client.get(
        "/api/news/events",
        params={
            "topic": "commodity_supply",
            "published_from": "2026-03-03T00:00:00Z",
            "published_to": "2026-03-03T23:59:59Z",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["scope"] == "hot"
    assert payload[0]["macro_topic"] == "commodity_supply"
    assert payload[0]["title"] == "国际油价高位震荡"


def test_news_events_endpoint_supports_pagination(news_client: TestClient) -> None:
    response = news_client.get(
        "/api/news/events",
        params={"page": 2, "page_size": 1},
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["title"] == "南方航空发布运力恢复公告"


def test_news_events_endpoint_defaults_to_latest_batch_versions(
    news_client: TestClient,
) -> None:
    _append_news_events(
        news_client,
        [
            NewsEvent(
                id="hot-archive-v2",
                scope="hot",
                cache_variant="global",
                ts_code=None,
                symbol=None,
                title="国际油价高位震荡",
                summary="新版归档批次",
                published_at=datetime(2026, 3, 3, 10, 0, tzinfo=UTC),
                url="https://finance.example.com/h/1",
                publisher=None,
                source="eastmoney_global",
                macro_topic="commodity_supply",
                fetched_at=datetime(2026, 3, 4, 10, 5, tzinfo=UTC),
            )
        ],
    )

    response = news_client.get("/api/news/events", params={"scope": "hot"})

    assert response.status_code == 200
    payload = response.json()
    duplicate_titles = [item for item in payload if item["title"] == "国际油价高位震荡"]
    assert len(duplicate_titles) == 1
    assert duplicate_titles[0]["summary"] == "新版归档批次"
    assert duplicate_titles[0]["fetched_at"] == "2026-03-04T10:05:00"


def test_news_events_endpoint_supports_batch_mode_all_for_archived_versions(
    news_client: TestClient,
) -> None:
    _append_news_events(
        news_client,
        [
            NewsEvent(
                id="hot-archive-v2-all",
                scope="hot",
                cache_variant="global",
                ts_code=None,
                symbol=None,
                title="国际油价高位震荡",
                summary="新版归档批次",
                published_at=datetime(2026, 3, 3, 10, 0, tzinfo=UTC),
                url="https://finance.example.com/h/1",
                publisher=None,
                source="eastmoney_global",
                macro_topic="commodity_supply",
                fetched_at=datetime(2026, 3, 4, 10, 5, tzinfo=UTC),
            )
        ],
    )

    response = news_client.get(
        "/api/news/events",
        params={"scope": "hot", "batch_mode": "all"},
    )

    assert response.status_code == 200
    payload = response.json()
    duplicate_titles = [item for item in payload if item["title"] == "国际油价高位震荡"]
    assert len(duplicate_titles) == 2
    assert duplicate_titles[0]["summary"] == "新版归档批次"
    assert duplicate_titles[1]["summary"] == "原油供需偏紧"


def test_news_events_endpoint_rejects_invalid_scope(news_client: TestClient) -> None:
    response = news_client.get(
        "/api/news/events",
        params={"scope": "macro"},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "invalid scope filter"


def test_news_events_endpoint_rejects_invalid_batch_mode(
    news_client: TestClient,
) -> None:
    response = news_client.get(
        "/api/news/events",
        params={"batch_mode": "snapshot"},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "invalid batch_mode filter"


def test_news_events_endpoint_rejects_reversed_time_range(
    news_client: TestClient,
) -> None:
    response = news_client.get(
        "/api/news/events",
        params={
            "published_from": "2026-03-04T00:00:00Z",
            "published_to": "2026-03-03T00:00:00Z",
        },
    )

    assert response.status_code == 422
    assert (
        response.json()["detail"]
        == "published_from must be earlier than or equal to published_to"
    )


def test_news_events_endpoint_rejects_zero_page(news_client: TestClient) -> None:
    response = news_client.get(
        "/api/news/events",
        params={"page": 0},
    )

    assert response.status_code == 422


def test_news_events_endpoint_rejects_zero_page_size(news_client: TestClient) -> None:
    response = news_client.get(
        "/api/news/events",
        params={"page_size": 0},
    )

    assert response.status_code == 422


def test_news_events_endpoint_rejects_oversized_page_size(
    news_client: TestClient,
) -> None:
    response = news_client.get(
        "/api/news/events",
        params={"page_size": 1001},
    )

    assert response.status_code == 422


def test_news_events_endpoint_orders_results_by_published_at_desc(
    news_client: TestClient,
) -> None:
    response = news_client.get(
        "/api/news/events",
        params={"page": 1, "page_size": 3},
    )

    assert response.status_code == 200
    payload = response.json()
    assert [item["title"] for item in payload] == [
        "国际油价高位震荡",
        "南方航空发布运力恢复公告",
        "美联储官员讲话",
    ]


def test_policy_news_route_returns_policy_scope(news_client: TestClient, monkeypatch) -> None:
    async def fake_fetch_policy_events() -> list[dict[str, object]]:
        return [
            {
                "title": "证监会调整监管框架",
                "summary": "加强数据披露要求",
                "published_at": "2026-03-02 10:00:00",
                "link": "https://politics.example.com/p/1",
            }
        ]

    monkeypatch.setattr(
        "app.api.routes.news.fetch_policy_events", fake_fetch_policy_events
    )

    response = news_client.get("/api/news/policy")

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["scope"] == "policy"
    assert payload[0]["source"] == "policy_gateway"


def test_policy_news_route_uses_cache_and_persists_batch(
    news_client: TestClient,
    monkeypatch,
) -> None:
    called = {"count": 0}

    async def fake_fetch_policy_events() -> list[dict[str, object]]:
        called["count"] += 1
        return [
            {
                "title": "证监会调整监管框架",
                "summary": "加强数据披露要求",
                "published_at": "2026-03-02 10:00:00",
                "link": "https://politics.example.com/p/1",
            }
        ]

    monkeypatch.setattr(
        "app.api.routes.news.fetch_policy_events",
        fake_fetch_policy_events,
    )

    first = news_client.get("/api/news/policy")
    second = news_client.get("/api/news/policy")

    assert first.status_code == 200
    assert second.status_code == 200
    assert called["count"] == 1
    batches = _load_news_fetch_batches(news_client, scope="policy")
    assert len(batches) == 1
    assert batches[0].status == "success"
    assert batches[0].trigger_source == "api.news.policy"
    assert "news:policy:policy_source:version" in news_client.fake_redis._store


def test_hot_news_route_reads_only_latest_archived_batch(
    news_client: TestClient,
    monkeypatch,
) -> None:
    _append_news_events(
        news_client,
        [
            NewsEvent(
                id="hot-latest-only",
                scope="hot",
                cache_variant="global",
                ts_code=None,
                symbol=None,
                title="归档后的最新热点",
                summary="仅最新批次可见",
                published_at=datetime(2026, 3, 25, 10, 0, tzinfo=UTC),
                url="https://finance.example.com/h/latest",
                publisher=None,
                source="eastmoney_global",
                macro_topic="commodity_supply",
                fetched_at=datetime(2026, 3, 25, 10, 5, tzinfo=UTC),
            )
        ],
    )

    async def fake_fetch_hot_news() -> list[dict[str, object]]:
        return []

    monkeypatch.setattr("app.api.routes.news.fetch_hot_news", fake_fetch_hot_news)

    response = news_client.get("/api/news/hot", params={"limit": 10})

    assert response.status_code == 200
    payload = response.json()
    assert [item["title"] for item in payload] == ["归档后的最新热点"]


def test_policy_news_route_falls_back_to_latest_archived_batch(
    news_client: TestClient,
    monkeypatch,
) -> None:
    _append_news_events(
        news_client,
        [
            NewsEvent(
                id="policy-archive-v1",
                scope="policy",
                cache_variant="policy_source",
                ts_code=None,
                symbol=None,
                title="旧政策批次",
                summary="旧政策摘要",
                published_at=datetime(2026, 3, 2, 10, 0, tzinfo=UTC),
                url="https://policy.example.com/old",
                publisher="政策源",
                source="policy_gateway",
                macro_topic="regulation_policy",
                fetched_at=datetime(2026, 3, 2, 10, 5, tzinfo=UTC),
            ),
            NewsEvent(
                id="policy-archive-v2",
                scope="policy",
                cache_variant="policy_source",
                ts_code=None,
                symbol=None,
                title="最新政策批次",
                summary="最新政策摘要",
                published_at=datetime(2026, 3, 5, 10, 0, tzinfo=UTC),
                url="https://policy.example.com/new",
                publisher="政策源",
                source="policy_gateway",
                macro_topic="regulation_policy",
                fetched_at=datetime(2026, 3, 5, 10, 5, tzinfo=UTC),
            ),
        ],
    )

    async def fake_fetch_policy_events() -> list[dict[str, object]]:
        return []

    monkeypatch.setattr(
        "app.api.routes.news.fetch_policy_events", fake_fetch_policy_events
    )

    response = news_client.get("/api/news/policy")

    assert response.status_code == 200
    payload = response.json()
    assert [item["title"] for item in payload] == ["最新政策批次"]


def test_stock_news_route_falls_back_to_latest_archived_batch_when_upstream_fails(
    news_client: TestClient,
    monkeypatch,
) -> None:
    _append_news_events(
        news_client,
        [
            NewsEvent(
                id="stock-archive-v2",
                scope="stock",
                cache_variant="with_announcements",
                ts_code="600029.SH",
                symbol="600029",
                title="南方航空最新归档批次",
                summary="只返回最新批次",
                published_at=datetime(2026, 3, 25, 9, 0, tzinfo=UTC),
                url="https://finance.example.com/s/latest",
                publisher="证券时报",
                source="eastmoney_stock",
                macro_topic=None,
                fetched_at=datetime(2026, 3, 25, 9, 5, tzinfo=UTC),
            )
        ],
    )

    async def fake_fetch_stock_news(_symbol: str) -> list[dict[str, object]]:
        raise RuntimeError("个股新闻上游不可用")

    async def fake_fetch_stock_announcements(*, symbol: str) -> list[dict[str, object]]:
        _ = symbol
        return []

    monkeypatch.setattr(
        "app.api.routes.stocks.fetch_stock_news",
        fake_fetch_stock_news,
    )
    monkeypatch.setattr(
        "app.api.routes.stocks.fetch_stock_announcements",
        fake_fetch_stock_announcements,
    )

    response = news_client.get("/api/stocks/600029.SH/news", params={"limit": 10})

    assert response.status_code == 200
    payload = response.json()
    assert [item["title"] for item in payload] == ["南方航空最新归档批次"]


def test_news_events_endpoint_supports_policy_scope(news_client: TestClient, monkeypatch) -> None:
    async def fake_fetch_policy_events() -> list[dict[str, object]]:
        return [
            {
                "title": "证监会发布监管新规",
                "summary": "强化信息披露要求",
                "published_at": "2026-03-05 08:00:00",
                "link": "https://policy.example.com/1",
            }
        ]

    monkeypatch.setattr(
        "app.api.routes.news.fetch_policy_events", fake_fetch_policy_events
    )

    policy_response = news_client.get("/api/news/policy")
    assert policy_response.status_code == 200

    response = news_client.get("/api/news/events", params={"scope": "policy"})

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["scope"] == "policy"
    assert payload[0]["title"] == "证监会发布监管新规"
