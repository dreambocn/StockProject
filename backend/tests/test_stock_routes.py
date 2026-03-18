import asyncio
from datetime import date
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.deps.auth import get_current_user
import app.api.routes.stocks as stocks_routes
from app.db.base import Base
from app.db.session import get_db_session
from app.main import app
from app.models.stock_daily_snapshot import StockDailySnapshot
from app.models.stock_instrument import StockInstrument
from app.models.user import User


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
def stock_client(tmp_path: Path) -> TestClient:
    db_path = tmp_path / "stock-test.db"
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
                        ts_code="000001.SZ",
                        symbol="000001",
                        name="平安银行",
                        fullname="平安银行股份有限公司",
                        area="深圳",
                        industry="银行",
                        market="主板",
                        exchange="SZSE",
                        list_status="L",
                        list_date=date(1991, 4, 3),
                        delist_date=None,
                        is_hs="S",
                    ),
                    StockInstrument(
                        ts_code="600000.SH",
                        symbol="600000",
                        name="浦发银行",
                        fullname="上海浦东发展银行股份有限公司",
                        area="上海",
                        industry="银行",
                        market="主板",
                        exchange="SSE",
                        list_status="L",
                        list_date=date(1999, 11, 10),
                        delist_date=None,
                        is_hs="H",
                    ),
                    StockInstrument(
                        ts_code="000004.SZ",
                        symbol="000004",
                        name="国农科技",
                        fullname="国农科技股份有限公司",
                        area="深圳",
                        industry="生物制药",
                        market="主板",
                        exchange="SZSE",
                        list_status="D",
                        list_date=date(1991, 1, 14),
                        delist_date=date(2024, 1, 30),
                        is_hs="N",
                    ),
                ]
            )
            session.add_all(
                [
                    StockDailySnapshot(
                        ts_code="000001.SZ",
                        trade_date=date(2026, 3, 3),
                        open=Decimal("11.00"),
                        high=Decimal("11.20"),
                        low=Decimal("10.80"),
                        close=Decimal("11.10"),
                        pre_close=Decimal("10.95"),
                        change=Decimal("0.15"),
                        pct_chg=Decimal("1.37"),
                        vol=Decimal("123456.00"),
                        amount=Decimal("789012.00"),
                        turnover_rate=Decimal("1.20"),
                        volume_ratio=Decimal("0.90"),
                        pe=Decimal("6.10"),
                        pb=Decimal("0.70"),
                        total_mv=Decimal("1000000.00"),
                        circ_mv=Decimal("900000.00"),
                    ),
                    StockDailySnapshot(
                        ts_code="600000.SH",
                        trade_date=date(2026, 3, 3),
                        open=Decimal("8.10"),
                        high=Decimal("8.30"),
                        low=Decimal("8.00"),
                        close=Decimal("8.25"),
                        pre_close=Decimal("8.05"),
                        change=Decimal("0.20"),
                        pct_chg=Decimal("2.48"),
                        vol=Decimal("654321.00"),
                        amount=Decimal("321098.00"),
                        turnover_rate=Decimal("1.80"),
                        volume_ratio=Decimal("1.10"),
                        pe=Decimal("5.80"),
                        pb=Decimal("0.62"),
                        total_mv=Decimal("2000000.00"),
                        circ_mv=Decimal("1800000.00"),
                    ),
                ]
            )
            await session.commit()

    fake_redis = FakeRedisClient()
    original_get_redis_client = stocks_routes.get_redis_client

    asyncio.run(_create_tables())
    asyncio.run(_seed_data())

    async def override_get_db_session():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session
    stocks_routes.get_redis_client = lambda: fake_redis

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()
    stocks_routes.get_redis_client = original_get_redis_client
    asyncio.run(engine.dispose())


def test_stocks_list_supports_keyword_search(stock_client: TestClient) -> None:
    response = stock_client.get("/api/stocks", params={"keyword": "平安"})

    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, list)
    assert len(payload) == 1
    assert payload[0]["ts_code"] == "000001.SZ"
    assert payload[0]["name"] == "平安银行"
    assert payload[0]["fullname"] == "平安银行股份有限公司"
    assert payload[0]["close"] == 11.1


def test_stocks_list_defaults_to_listed_only(stock_client: TestClient) -> None:
    response = stock_client.get("/api/stocks")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 2
    assert {item["ts_code"] for item in payload} == {"000001.SZ", "600000.SH"}


def test_stocks_list_supports_explicit_status_filter(stock_client: TestClient) -> None:
    response = stock_client.get("/api/stocks", params={"list_status": "L,D"})

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 3
    assert {item["ts_code"] for item in payload} == {
        "000001.SZ",
        "600000.SH",
        "000004.SZ",
    }


def test_stocks_list_supports_all_status_filter(stock_client: TestClient) -> None:
    response = stock_client.get("/api/stocks", params={"list_status": "ALL"})

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 3


def test_stocks_list_rejects_invalid_status_filter(stock_client: TestClient) -> None:
    response = stock_client.get("/api/stocks", params={"list_status": "X"})

    assert response.status_code == 422
    payload = response.json()
    assert payload["detail"] == (
        "invalid list_status, expected ALL or comma-separated values in L,D,P,G"
    )


def test_stock_detail_returns_latest_snapshot(stock_client: TestClient) -> None:
    response = stock_client.get("/api/stocks/600000.SH")

    assert response.status_code == 200
    payload = response.json()
    assert payload["instrument"]["ts_code"] == "600000.SH"
    assert payload["latest_snapshot"]["trade_date"] == "2026-03-03"
    assert payload["latest_snapshot"]["close"] == 8.25


def test_stocks_list_backfills_price_and_date_from_kline_db(
    stock_client: TestClient, monkeypatch
) -> None:
    called: dict[str, object] = {
        "count": 0,
    }

    class FakeTushareGateway:
        def __init__(self, token: str) -> None:
            called["token"] = token

        async def fetch_daily_by_range(
            self,
            *,
            ts_code: str,
            start_date: str,
            end_date: str,
        ) -> list[dict[str, object]]:
            called["count"] = int(called["count"]) + 1
            called["ts_code"] = ts_code
            called["start_date"] = start_date
            called["end_date"] = end_date
            return [
                {
                    "ts_code": ts_code,
                    "trade_date": "20260304",
                    "open": 12.1,
                    "high": 12.4,
                    "low": 11.9,
                    "close": 12.25,
                    "pre_close": 12.0,
                    "change": 0.25,
                    "pct_chg": 2.08,
                    "vol": 567000,
                    "amount": 830000,
                }
            ]

    fake_redis = FakeRedisClient()
    monkeypatch.setattr("app.api.routes.stocks.TushareGateway", FakeTushareGateway)
    monkeypatch.setattr("app.api.routes.stocks.get_redis_client", lambda: fake_redis)

    seed_daily_response = stock_client.get(
        "/api/stocks/000004.SZ/daily",
        params={
            "period": "daily",
            "limit": 1,
            "start_date": "20260301",
            "end_date": "20260305",
        },
    )
    assert seed_daily_response.status_code == 200
    assert called["count"] == 1

    list_response = stock_client.get(
        "/api/stocks",
        params={
            "keyword": "000004",
            "list_status": "ALL",
        },
    )

    assert list_response.status_code == 200
    payload = list_response.json()
    assert len(payload) == 1
    assert payload[0]["ts_code"] == "000004.SZ"
    assert payload[0]["close"] == 12.25
    assert payload[0]["pct_chg"] == 2.08
    assert payload[0]["trade_date"] == "2026-03-04"
    assert called["count"] == 1


def test_stocks_list_falls_back_to_tushare_and_persists_latest_quote(
    stock_client: TestClient, monkeypatch
) -> None:
    called: dict[str, object] = {
        "count": 0,
    }

    class FakeTushareGateway:
        def __init__(self, token: str) -> None:
            called["token"] = token

        async def fetch_daily_by_range(
            self,
            *,
            ts_code: str,
            start_date: str,
            end_date: str,
        ) -> list[dict[str, object]]:
            called["count"] = int(called["count"]) + 1
            called["ts_code"] = ts_code
            called["start_date"] = start_date
            called["end_date"] = end_date
            return [
                {
                    "ts_code": ts_code,
                    "trade_date": "20260305",
                    "open": 12.3,
                    "high": 12.8,
                    "low": 12.0,
                    "close": 12.6,
                    "pre_close": 12.25,
                    "change": 0.35,
                    "pct_chg": 2.86,
                    "vol": 620000,
                    "amount": 910000,
                }
            ]

    monkeypatch.setattr("app.api.routes.stocks.TushareGateway", FakeTushareGateway)

    first_response = stock_client.get(
        "/api/stocks",
        params={
            "keyword": "000004",
            "list_status": "ALL",
        },
    )

    assert first_response.status_code == 200
    first_payload = first_response.json()
    assert len(first_payload) == 1
    assert first_payload[0]["close"] == 12.6
    assert first_payload[0]["trade_date"] == "2026-03-05"
    assert called["count"] == 1

    second_response = stock_client.get(
        "/api/stocks",
        params={
            "keyword": "000004",
            "list_status": "ALL",
        },
    )

    assert second_response.status_code == 200
    second_payload = second_response.json()
    assert len(second_payload) == 1
    assert second_payload[0]["close"] == 12.6
    assert second_payload[0]["trade_date"] == "2026-03-05"
    assert called["count"] == 1


def test_stock_daily_returns_recent_records(
    stock_client: TestClient, monkeypatch
) -> None:
    called: dict[str, object] = {
        "count": 0,
    }

    class FakeTushareGateway:
        def __init__(self, token: str) -> None:
            called["token"] = token

        async def fetch_daily_by_range(
            self,
            *,
            ts_code: str,
            start_date: str,
            end_date: str,
        ) -> list[dict[str, object]]:
            called["count"] = int(called["count"]) + 1
            called["ts_code"] = ts_code
            called["start_date"] = start_date
            called["end_date"] = end_date
            return [
                {
                    "ts_code": "000001.SZ",
                    "trade_date": "20260303",
                    "open": 11.0,
                    "high": 11.2,
                    "low": 10.8,
                    "close": 11.1,
                    "pre_close": 10.95,
                    "change": 0.15,
                    "pct_chg": 1.37,
                    "vol": 123456,
                    "amount": 789012,
                },
                {
                    "ts_code": "000001.SZ",
                    "trade_date": "20260302",
                    "open": 10.9,
                    "high": 11.0,
                    "low": 10.7,
                    "close": 10.95,
                    "pre_close": 10.9,
                    "change": 0.05,
                    "pct_chg": 0.46,
                    "vol": 100000,
                    "amount": 680000,
                },
            ]

    fake_redis = FakeRedisClient()
    monkeypatch.setattr("app.api.routes.stocks.TushareGateway", FakeTushareGateway)
    monkeypatch.setattr("app.api.routes.stocks.get_redis_client", lambda: fake_redis)

    response = stock_client.get(
        "/api/stocks/000001.SZ/daily",
        params={"limit": 1, "start_date": "20260301", "end_date": "20260303"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["trade_date"] == "2026-03-03"
    assert payload[0]["pct_chg"] == 1.37
    assert payload[0]["ts_code"] == "000001.SZ"
    assert called["count"] == 1
    assert called["ts_code"] == "000001.SZ"
    assert called["start_date"] == "20260301"
    assert called["end_date"] == "20260303"

    response_cached = stock_client.get(
        "/api/stocks/000001.SZ/daily",
        params={"limit": 1, "start_date": "20260301", "end_date": "20260303"},
    )
    assert response_cached.status_code == 200
    cached_payload = response_cached.json()
    assert len(cached_payload) == 1
    assert cached_payload[0]["trade_date"] == "2026-03-03"
    assert called["count"] == 1


def test_stock_daily_supports_weekly_period_and_prefers_db(
    stock_client: TestClient, monkeypatch
) -> None:
    called: dict[str, object] = {
        "count": 0,
    }

    class FakeTushareGateway:
        def __init__(self, token: str) -> None:
            called["token"] = token

        async def fetch_weekly_by_range(
            self,
            *,
            ts_code: str,
            start_date: str,
            end_date: str,
        ) -> list[dict[str, object]]:
            called["count"] = int(called["count"]) + 1
            called["ts_code"] = ts_code
            called["start_date"] = start_date
            called["end_date"] = end_date
            return [
                {
                    "ts_code": ts_code,
                    "trade_date": "20260306",
                    "open": 11.0,
                    "high": 11.8,
                    "low": 10.7,
                    "close": 11.5,
                    "pre_close": 10.9,
                    "change": 0.6,
                    "pct_chg": 5.5,
                    "vol": 900000,
                    "amount": 1000000,
                }
            ]

    fake_redis = FakeRedisClient()
    monkeypatch.setattr("app.api.routes.stocks.TushareGateway", FakeTushareGateway)
    monkeypatch.setattr("app.api.routes.stocks.get_redis_client", lambda: fake_redis)

    response = stock_client.get(
        "/api/stocks/000001.SZ/daily",
        params={
            "period": "weekly",
            "limit": 1,
            "start_date": "20260301",
            "end_date": "20260310",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["trade_date"] == "2026-03-06"
    assert called["count"] == 1

    fake_redis._store.clear()

    response_from_db = stock_client.get(
        "/api/stocks/000001.SZ/daily",
        params={
            "period": "weekly",
            "limit": 1,
            "start_date": "20260301",
            "end_date": "20260310",
        },
    )

    assert response_from_db.status_code == 200
    payload_from_db = response_from_db.json()
    assert len(payload_from_db) == 1
    assert payload_from_db[0]["trade_date"] == "2026-03-06"
    assert called["count"] == 1


def test_trade_calendar_prefers_db_then_falls_back_to_tushare(
    stock_client: TestClient, monkeypatch
) -> None:
    called: dict[str, object] = {
        "count": 0,
    }

    class FakeTushareGateway:
        def __init__(self, token: str) -> None:
            called["token"] = token

        async def fetch_trade_cal_by_range(
            self,
            *,
            exchange: str,
            start_date: str,
            end_date: str,
            is_open: str | None,
        ) -> list[dict[str, object]]:
            called["count"] = int(called["count"]) + 1
            called["exchange"] = exchange
            called["start_date"] = start_date
            called["end_date"] = end_date
            called["is_open"] = is_open
            return [
                {
                    "exchange": exchange,
                    "cal_date": "20260303",
                    "is_open": "1",
                    "pretrade_date": "20260302",
                }
            ]

    fake_redis = FakeRedisClient()
    monkeypatch.setattr("app.api.routes.stocks.TushareGateway", FakeTushareGateway)
    monkeypatch.setattr("app.api.routes.stocks.get_redis_client", lambda: fake_redis)

    response = stock_client.get(
        "/api/stocks/trade-cal",
        params={
            "exchange": "SSE",
            "start_date": "20260301",
            "end_date": "20260305",
            "is_open": "1",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["exchange"] == "SSE"
    assert payload[0]["cal_date"] == "2026-03-03"
    assert payload[0]["is_open"] == "1"
    assert called["count"] == 1

    fake_redis._store.clear()

    response_from_db = stock_client.get(
        "/api/stocks/trade-cal",
        params={
            "exchange": "SSE",
            "start_date": "20260301",
            "end_date": "20260305",
            "is_open": "1",
        },
    )

    assert response_from_db.status_code == 200
    payload_from_db = response_from_db.json()
    assert len(payload_from_db) == 1
    assert payload_from_db[0]["cal_date"] == "2026-03-03"
    assert called["count"] == 1


def test_adj_factor_prefers_db_then_falls_back_to_tushare(
    stock_client: TestClient, monkeypatch
) -> None:
    called: dict[str, object] = {
        "count": 0,
    }

    class FakeTushareGateway:
        def __init__(self, token: str) -> None:
            called["token"] = token

        async def fetch_adj_factor_by_range(
            self,
            *,
            ts_code: str,
            start_date: str,
            end_date: str,
        ) -> list[dict[str, object]]:
            called["count"] = int(called["count"]) + 1
            called["ts_code"] = ts_code
            called["start_date"] = start_date
            called["end_date"] = end_date
            return [
                {
                    "ts_code": ts_code,
                    "trade_date": "20260303",
                    "adj_factor": 1.2345,
                }
            ]

    fake_redis = FakeRedisClient()
    monkeypatch.setattr("app.api.routes.stocks.TushareGateway", FakeTushareGateway)
    monkeypatch.setattr("app.api.routes.stocks.get_redis_client", lambda: fake_redis)

    response = stock_client.get(
        "/api/stocks/000001.SZ/adj-factor",
        params={
            "limit": 1,
            "start_date": "20260301",
            "end_date": "20260305",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["ts_code"] == "000001.SZ"
    assert payload[0]["trade_date"] == "2026-03-03"
    assert payload[0]["adj_factor"] == 1.2345
    assert called["count"] == 1

    fake_redis._store.clear()

    response_from_db = stock_client.get(
        "/api/stocks/000001.SZ/adj-factor",
        params={
            "limit": 1,
            "start_date": "20260301",
            "end_date": "20260305",
        },
    )

    assert response_from_db.status_code == 200
    payload_from_db = response_from_db.json()
    assert len(payload_from_db) == 1
    assert payload_from_db[0]["adj_factor"] == 1.2345
    assert called["count"] == 1


def test_trigger_stock_basic_full_sync_endpoint(
    stock_client: TestClient, monkeypatch
) -> None:
    called: dict[str, object] = {}

    class FakeGateway:
        def __init__(self, token: str) -> None:
            called["token"] = token

    async def fake_sync_stock_basic_full(
        session, gateway, list_statuses=None
    ) -> dict[str, object]:
        called["session_present"] = session is not None
        called["gateway"] = gateway.__class__.__name__
        called["list_statuses"] = list_statuses
        return {
            "total": 3000,
            "created": 20,
            "updated": 2980,
            "list_statuses": ["L", "D", "P", "G"],
        }

    async def override_get_current_user() -> User:
        return User(
            id="test-user-id",
            username="tester",
            email="tester@example.com",
            password_hash="x",
            is_active=True,
        )

    monkeypatch.setattr("app.api.routes.stocks.TushareGateway", FakeGateway)
    monkeypatch.setattr(
        "app.api.routes.stocks.sync_stock_basic_full", fake_sync_stock_basic_full
    )
    app.dependency_overrides[get_current_user] = override_get_current_user

    response = stock_client.post("/api/stocks/sync/full")

    assert response.status_code == 200
    payload = response.json()
    assert payload["message"] == "stock basic sync completed"
    assert payload["total"] == 3000
    assert payload["created"] == 20
    assert payload["updated"] == 2980
    assert payload["list_statuses"] == ["L", "D", "P", "G"]
    assert called["session_present"] is True
    assert called["gateway"] == "FakeGateway"


def test_stock_related_news_returns_symbol_scoped_items(
    stock_client: TestClient, monkeypatch
) -> None:
    async def fake_fetch_stock_news(symbol: str) -> list[dict[str, object]]:
        assert symbol == "600000"
        return [
            {
                "关键词": "600000",
                "新闻标题": "浦发银行发布业绩快报",
                "新闻内容": "营收同比增长",
                "发布时间": "2026-03-03 09:12:00",
                "文章来源": "东方财富",
                "新闻链接": "https://finance.example.com/a/1",
            }
        ]

    monkeypatch.setattr(
        "app.api.routes.stocks.fetch_stock_news",
        fake_fetch_stock_news,
    )

    response = stock_client.get("/api/stocks/600000.SH/news")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["symbol"] == "600000"
    assert payload[0]["ts_code"] == "600000.SH"
    assert payload[0]["title"] == "浦发银行发布业绩快报"


def test_stock_related_news_uses_cache_and_avoids_repeat_upstream_calls(
    stock_client: TestClient, monkeypatch
) -> None:
    called = {"news": 0, "announcements": 0}

    async def fake_fetch_stock_news(symbol: str) -> list[dict[str, object]]:
        called["news"] += 1
        assert symbol == "600000"
        return [
            {
                "关键词": "600000",
                "新闻标题": "浦发银行发布业绩快报",
                "新闻内容": "营收同比增长",
                "发布时间": "2026-03-03 09:12:00",
                "文章来源": "东方财富",
                "新闻链接": "https://finance.example.com/a/1",
            }
        ]

    async def fake_fetch_stock_announcements(
        *,
        symbol: str,
        market: str = "沪深京",
        keyword: str = "",
        category: str = "",
        start_date: str = "",
        end_date: str = "",
    ) -> list[dict[str, object]]:
        _ = market, keyword, category, start_date, end_date
        called["announcements"] += 1
        assert symbol == "600000"
        return [
            {
                "公告标题": "浦发银行关于董事会决议的公告",
                "公告时间": "2026-03-03 08:30:00",
                "公告链接": "https://finance.example.com/notice/1",
            }
        ]

    monkeypatch.setattr(
        "app.api.routes.stocks.fetch_stock_news",
        fake_fetch_stock_news,
    )
    monkeypatch.setattr(
        "app.api.routes.stocks.fetch_stock_announcements",
        fake_fetch_stock_announcements,
    )

    first = stock_client.get("/api/stocks/600000.SH/news")
    second = stock_client.get("/api/stocks/600000.SH/news")

    assert first.status_code == 200
    assert second.status_code == 200
    assert called["news"] == 1
    assert called["announcements"] == 1
    assert len(second.json()) == 2
