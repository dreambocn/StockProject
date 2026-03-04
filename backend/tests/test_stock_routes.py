import asyncio
from datetime import date
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.deps.auth import get_current_user
from app.db.base import Base
from app.db.session import get_db_session
from app.main import app
from app.models.stock_daily_snapshot import StockDailySnapshot
from app.models.stock_instrument import StockInstrument
from app.models.user import User


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

    asyncio.run(_create_tables())
    asyncio.run(_seed_data())

    async def override_get_db_session():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()
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


def test_stock_daily_returns_recent_records(stock_client: TestClient) -> None:
    response = stock_client.get("/api/stocks/000001.SZ/daily", params={"limit": 20})

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["trade_date"] == "2026-03-03"
    assert payload[0]["pct_chg"] == 1.37


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
