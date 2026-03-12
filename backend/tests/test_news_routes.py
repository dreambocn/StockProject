from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.session import get_db_session
from app.main import app
from app.models.stock_instrument import StockInstrument


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
                ]
            )
            await session.commit()

    import asyncio

    asyncio.run(_create_tables())
    asyncio.run(_seed_data())

    async def _override_session():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_db_session] = _override_session

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.pop(get_db_session, None)
    asyncio.run(engine.dispose())


def test_hot_news_route_calls_gateway_once(monkeypatch) -> None:
    called = {"count": 0}

    async def fake_fetch_hot_news() -> list[dict[str, object]]:
        called["count"] += 1
        return []

    monkeypatch.setattr("app.api.routes.news.fetch_hot_news", fake_fetch_hot_news)

    with TestClient(app) as client:
        response = client.get("/api/news/hot")

    assert response.status_code == 200
    assert called["count"] == 1


def test_hot_news_response_contains_normalized_fields(monkeypatch) -> None:
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

    with TestClient(app) as client:
        response = client.get("/api/news/hot")

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["title"] == "中东局势升级"
    assert payload[0]["summary"] == "避险情绪升温"
    assert payload[0]["published_at"] == "2026-03-03T09:00:00"
    assert payload[0]["source"] == "eastmoney_global"
    assert payload[0]["macro_topic"] == "geopolitical_conflict"


def test_hot_news_supports_macro_topic_filter(monkeypatch) -> None:
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

    with TestClient(app) as client:
        response = client.get(
            "/api/news/hot",
            params={"topic": "geopolitical_conflict"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["title"] == "中东局势升级引发避险情绪"
    assert payload[0]["macro_topic"] == "geopolitical_conflict"


def test_hot_news_upstream_error_returns_503(monkeypatch) -> None:
    async def fake_fetch_hot_news() -> list[dict[str, object]]:
        raise RuntimeError("upstream down")

    monkeypatch.setattr("app.api.routes.news.fetch_hot_news", fake_fetch_hot_news)

    with TestClient(app) as client:
        response = client.get("/api/news/hot")

    assert response.status_code == 503
    assert response.json()["detail"] == "hot news upstream unavailable"


def test_impact_map_endpoint_returns_profiles(news_client: TestClient) -> None:
    response = news_client.get("/api/news/impact-map")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) > 0
    assert payload[0]["topic"]
    assert isinstance(payload[0]["beneficiary_sectors"], list)


def test_impact_map_endpoint_supports_topic_filter() -> None:
    with TestClient(app) as client:
        response = client.get(
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
