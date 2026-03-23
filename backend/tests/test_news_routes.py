from datetime import UTC, date, datetime
from pathlib import Path

from fastapi.testclient import TestClient
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.session import get_db_session
from app.main import app
import app.api.routes.news as news_routes
from app.models.news_event import NewsEvent
from app.models.stock_instrument import StockInstrument


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

    asyncio.run(_create_tables())
    asyncio.run(_seed_data())

    async def _override_session():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_db_session] = _override_session
    news_routes.get_redis_client = lambda: fake_redis

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.pop(get_db_session, None)
    news_routes.get_redis_client = original_get_redis_client
    asyncio.run(engine.dispose())


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
    assert response.json() == []


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


def test_news_events_endpoint_rejects_invalid_scope(news_client: TestClient) -> None:
    response = news_client.get(
        "/api/news/events",
        params={"scope": "macro"},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "invalid scope filter"


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
