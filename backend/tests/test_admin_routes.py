import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.security import create_access_token, hash_password
from app.db.base import Base
from app.db.session import get_db_session
from app.main import app
from app.models.user import User


@pytest.fixture
def admin_test_context(tmp_path: Path):
    db_path = tmp_path / "admin-test.db"
    db_url = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    engine = create_async_engine(db_url)
    test_session_maker = async_sessionmaker(engine, expire_on_commit=False)

    async def _create_tables() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(_create_tables())

    async def override_get_db_session():
        async with test_session_maker() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session

    with TestClient(app) as client:
        yield {
            "client": client,
            "session_maker": test_session_maker,
        }

    app.dependency_overrides.clear()
    asyncio.run(engine.dispose())


def _create_user(
    session_maker: async_sessionmaker,
    username: str,
    email: str,
    user_level: str,
) -> User:
    async def _create() -> User:
        async with session_maker() as session:
            user = User(
                username=username,
                email=email,
                password_hash=hash_password("StrongP@ss1"),
                user_level=user_level,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            return user

    return asyncio.run(_create())


def test_admin_user_list_rejects_non_admin(admin_test_context) -> None:
    user = _create_user(
        admin_test_context["session_maker"],
        username="normal-user",
        email="normal@example.com",
        user_level="user",
    )
    access_token = create_access_token(user.id)

    response = admin_test_context["client"].get(
        "/api/admin/users",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 403


def test_admin_can_list_and_create_users(admin_test_context) -> None:
    admin_user = _create_user(
        admin_test_context["session_maker"],
        username="root-admin",
        email="root@example.com",
        user_level="admin",
    )
    admin_access_token = create_access_token(admin_user.id)

    create_response = admin_test_context["client"].post(
        "/api/admin/users",
        headers={"Authorization": f"Bearer {admin_access_token}"},
        json={
            "username": "ops-user",
            "email": "ops@example.com",
            "password": "StrongP@ss2",
            "user_level": "user",
        },
    )
    assert create_response.status_code == 201
    assert create_response.json()["username"] == "ops-user"
    assert create_response.json()["user_level"] == "user"

    list_response = admin_test_context["client"].get(
        "/api/admin/users",
        headers={"Authorization": f"Bearer {admin_access_token}"},
    )
    assert list_response.status_code == 200
    users = list_response.json()
    assert len(users) == 2
    assert any(item["user_level"] == "admin" for item in users)


def test_admin_stocks_full_rejects_non_admin(admin_test_context) -> None:
    user = _create_user(
        admin_test_context["session_maker"],
        username="normal-user-2",
        email="normal2@example.com",
        user_level="user",
    )
    access_token = create_access_token(user.id)

    response = admin_test_context["client"].post(
        "/api/admin/stocks/full",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 403


def test_admin_can_sync_full_and_query_stocks_with_pagination(
    admin_test_context, monkeypatch
) -> None:
    called: dict[str, object] = {}

    class FakeGateway:
        def __init__(self, token: str) -> None:
            called["token"] = token

        async def fetch_stock_basic_by_status(
            self, list_status: str
        ) -> list[dict[str, str]]:
            called.setdefault("statuses", []).append(list_status)
            payload_map: dict[str, list[dict[str, str]]] = {
                "L": [
                    {
                        "ts_code": "000001.SZ",
                        "symbol": "000001",
                        "name": "平安银行",
                        "area": "深圳",
                        "industry": "银行",
                        "fullname": "平安银行股份有限公司",
                        "enname": "Ping An Bank",
                        "cnspell": "payh",
                        "market": "主板",
                        "exchange": "SZSE",
                        "curr_type": "CNY",
                        "list_status": "L",
                        "list_date": "19910403",
                        "delist_date": "",
                        "is_hs": "S",
                        "act_name": "平安银行",
                        "act_ent_type": "银行",
                    }
                ],
                "D": [
                    {
                        "ts_code": "000004.SZ",
                        "symbol": "000004",
                        "name": "国农科技",
                        "area": "深圳",
                        "industry": "生物制药",
                        "fullname": "国农科技股份有限公司",
                        "enname": "Guonong Tech",
                        "cnspell": "gnkj",
                        "market": "主板",
                        "exchange": "SZSE",
                        "curr_type": "CNY",
                        "list_status": "D",
                        "list_date": "19910114",
                        "delist_date": "20240130",
                        "is_hs": "N",
                        "act_name": "国农科技",
                        "act_ent_type": "企业",
                    }
                ],
                "P": [],
                "G": [],
            }
            return payload_map.get(list_status, [])

    monkeypatch.setattr("app.api.routes.admin.TushareGateway", FakeGateway)
    monkeypatch.setattr(
        "app.api.routes.admin.get_settings",
        lambda: SimpleNamespace(tushare_token="mock-token"),
    )

    admin_user = _create_user(
        admin_test_context["session_maker"],
        username="stock-admin",
        email="stock-admin@example.com",
        user_level="admin",
    )
    access_token = create_access_token(admin_user.id)

    sync_response = admin_test_context["client"].post(
        "/api/admin/stocks/full?list_status=L,D",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert sync_response.status_code == 200
    sync_payload = sync_response.json()
    assert sync_payload["total"] == 2
    assert sync_payload["created"] == 2
    assert sync_payload["updated"] == 0
    assert sync_payload["list_statuses"] == ["L", "D"]

    list_response_page_1 = admin_test_context["client"].get(
        "/api/admin/stocks?list_status=ALL&page=1&page_size=1",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert list_response_page_1.status_code == 200
    page_1_payload = list_response_page_1.json()
    assert page_1_payload["total"] == 2
    assert page_1_payload["page"] == 1
    assert page_1_payload["page_size"] == 1
    assert len(page_1_payload["items"]) == 1
    assert page_1_payload["items"][0]["ts_code"] == "000001.SZ"

    list_response_page_2 = admin_test_context["client"].get(
        "/api/admin/stocks?list_status=ALL&page=2&page_size=1",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert list_response_page_2.status_code == 200
    page_2_payload = list_response_page_2.json()
    assert page_2_payload["total"] == 2
    assert page_2_payload["page"] == 2
    assert page_2_payload["page_size"] == 1
    assert len(page_2_payload["items"]) == 1
    assert page_2_payload["items"][0]["ts_code"] == "000004.SZ"

    filtered_response = admin_test_context["client"].get(
        "/api/admin/stocks?keyword=%E5%9B%BD%E5%86%9C&list_status=ALL&page=1&page_size=20",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert filtered_response.status_code == 200
    filtered_payload = filtered_response.json()
    assert filtered_payload["total"] == 1
    assert len(filtered_payload["items"]) == 1
    assert filtered_payload["items"][0]["ts_code"] == "000004.SZ"

    assert called["token"] == "mock-token"
    assert called["statuses"] == ["L", "D"]
