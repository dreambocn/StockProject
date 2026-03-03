import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.deps.auth import get_login_challenge_store, get_token_store
from app.db.base import Base
from app.db.session import get_db_session
from app.main import app


class InMemoryTokenStore:
    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    async def set_refresh_token(
        self, jti: str, user_id: str, expires_seconds: int
    ) -> None:
        self._store[jti] = user_id

    async def validate_refresh_token(self, jti: str, user_id: str) -> bool:
        return self._store.get(jti) == user_id

    async def revoke_refresh_token(self, jti: str) -> None:
        self._store.pop(jti, None)


class InMemoryLoginChallengeStore:
    def __init__(self) -> None:
        self.failures: dict[str, int] = {}
        self.captchas: dict[str, str] = {}

    async def record_failed_login(self, identity_key: str, window_seconds: int) -> int:
        current = self.failures.get(identity_key, 0) + 1
        self.failures[identity_key] = current
        return current

    async def get_failed_login_count(self, identity_key: str) -> int:
        return self.failures.get(identity_key, 0)

    async def reset_failed_login_count(self, identity_key: str) -> None:
        self.failures.pop(identity_key, None)

    async def set_captcha_challenge(
        self, captcha_id: str, answer: str, expires_seconds: int
    ) -> None:
        self.captchas[captcha_id] = "ABCD"

    async def validate_captcha_challenge(self, captcha_id: str, answer: str) -> bool:
        return self.captchas.get(captcha_id) == answer

    async def revoke_captcha_challenge(self, captcha_id: str) -> None:
        self.captchas.pop(captcha_id, None)


@pytest.fixture
def auth_client(tmp_path: Path) -> TestClient:
    db_path = tmp_path / "auth-test.db"
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

    token_store = InMemoryTokenStore()
    login_challenge_store = InMemoryLoginChallengeStore()
    app.dependency_overrides[get_db_session] = override_get_db_session
    app.dependency_overrides[get_token_store] = lambda: token_store
    app.dependency_overrides[get_login_challenge_store] = lambda: login_challenge_store

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()
    asyncio.run(engine.dispose())


def test_register_login_refresh_change_password_logout_flow(
    auth_client: TestClient,
) -> None:
    register_response = auth_client.post(
        "/api/auth/register",
        json={
            "username": "alice",
            "email": "alice@example.com",
            "password": "Passw0rd!123",
        },
    )
    assert register_response.status_code == 201
    assert register_response.json()["username"] == "alice"

    login_response = auth_client.post(
        "/api/auth/login",
        json={"account": "alice", "password": "Passw0rd!123"},
    )
    assert login_response.status_code == 200
    login_payload = login_response.json()
    assert login_payload["token_type"] == "bearer"
    assert login_payload["access_token"]
    assert login_payload["refresh_token"]

    me_response = auth_client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {login_payload['access_token']}"},
    )
    assert me_response.status_code == 200
    assert me_response.json()["email"] == "alice@example.com"

    change_password_response = auth_client.post(
        "/api/auth/change-password",
        json={"current_password": "Passw0rd!123", "new_password": "N3wPass!456"},
        headers={"Authorization": f"Bearer {login_payload['access_token']}"},
    )
    assert change_password_response.status_code == 200

    old_login_response = auth_client.post(
        "/api/auth/login",
        json={"account": "alice", "password": "Passw0rd!123"},
    )
    assert old_login_response.status_code == 401

    new_login_response = auth_client.post(
        "/api/auth/login",
        json={"account": "alice", "password": "N3wPass!456"},
    )
    assert new_login_response.status_code == 200

    refresh_response = auth_client.post(
        "/api/auth/refresh",
        json={"refresh_token": new_login_response.json()["refresh_token"]},
    )
    assert refresh_response.status_code == 200
    rotated_refresh_token = refresh_response.json()["refresh_token"]

    logout_response = auth_client.post(
        "/api/auth/logout",
        json={"refresh_token": rotated_refresh_token},
    )
    assert logout_response.status_code == 200

    refresh_after_logout_response = auth_client.post(
        "/api/auth/refresh",
        json={"refresh_token": rotated_refresh_token},
    )
    assert refresh_after_logout_response.status_code == 401


def test_login_supports_username_or_email(auth_client: TestClient) -> None:
    register_response = auth_client.post(
        "/api/auth/register",
        json={
            "username": "bob",
            "email": "bob@example.com",
            "password": "B0bPass!123",
        },
    )
    assert register_response.status_code == 201

    login_by_username_response = auth_client.post(
        "/api/auth/login",
        json={"account": "bob", "password": "B0bPass!123"},
    )
    assert login_by_username_response.status_code == 200

    login_by_email_response = auth_client.post(
        "/api/auth/login",
        json={"account": "bob@example.com", "password": "B0bPass!123"},
    )
    assert login_by_email_response.status_code == 200


def test_register_rejects_weak_password(auth_client: TestClient) -> None:
    register_response = auth_client.post(
        "/api/auth/register",
        json={
            "username": "charlie",
            "email": "charlie@example.com",
            "password": "weakpass",
        },
    )

    assert register_response.status_code == 422
    assert "Password" in str(register_response.json())


def test_change_password_rejects_weak_new_password(auth_client: TestClient) -> None:
    register_response = auth_client.post(
        "/api/auth/register",
        json={
            "username": "dora",
            "email": "dora@example.com",
            "password": "StrongP@ss1",
        },
    )
    assert register_response.status_code == 201

    login_response = auth_client.post(
        "/api/auth/login",
        json={"account": "dora", "password": "StrongP@ss1"},
    )
    assert login_response.status_code == 200

    change_password_response = auth_client.post(
        "/api/auth/change-password",
        json={"current_password": "StrongP@ss1", "new_password": "weakpass"},
        headers={"Authorization": f"Bearer {login_response.json()['access_token']}"},
    )

    assert change_password_response.status_code == 422
    assert "Password" in str(change_password_response.json())


def test_login_requires_captcha_after_two_failed_attempts(
    auth_client: TestClient,
) -> None:
    register_response = auth_client.post(
        "/api/auth/register",
        json={
            "username": "eve",
            "email": "eve@example.com",
            "password": "StrongP@ss1",
        },
    )
    assert register_response.status_code == 201

    first_failed_login = auth_client.post(
        "/api/auth/login",
        json={"account": "eve", "password": "wrongpass"},
    )
    second_failed_login = auth_client.post(
        "/api/auth/login",
        json={"account": "eve", "password": "wrongpass"},
    )
    third_failed_login = auth_client.post(
        "/api/auth/login",
        json={"account": "eve", "password": "wrongpass"},
    )

    assert first_failed_login.status_code == 401
    assert second_failed_login.status_code == 401
    assert third_failed_login.status_code == 401
    detail = third_failed_login.json()["detail"]
    assert detail["captcha_required"] is True


def test_get_captcha_challenge_returns_image_and_id(auth_client: TestClient) -> None:
    response = auth_client.get("/api/auth/captcha")

    assert response.status_code == 200
    payload = response.json()
    assert payload["captcha_id"]
    assert payload["image_base64"]
    assert payload["expires_in"] > 0


def test_login_rejects_missing_or_invalid_captcha_after_threshold(
    auth_client: TestClient,
) -> None:
    auth_client.post(
        "/api/auth/register",
        json={
            "username": "frank",
            "email": "frank@example.com",
            "password": "StrongP@ss1",
        },
    )

    auth_client.post(
        "/api/auth/login",
        json={"account": "frank", "password": "wrongpass"},
    )
    auth_client.post(
        "/api/auth/login",
        json={"account": "frank", "password": "wrongpass"},
    )

    missing_captcha_response = auth_client.post(
        "/api/auth/login",
        json={"account": "frank", "password": "StrongP@ss1"},
    )
    assert missing_captcha_response.status_code == 401
    assert (
        missing_captcha_response.json()["detail"]["captcha_reason"] == "captcha_missing"
    )

    captcha_response = auth_client.get("/api/auth/captcha")
    assert captcha_response.status_code == 200
    captcha_payload = captcha_response.json()

    invalid_captcha_response = auth_client.post(
        "/api/auth/login",
        json={
            "account": "frank",
            "password": "StrongP@ss1",
            "captcha_id": captcha_payload["captcha_id"],
            "captcha_code": "ZZZZ",
        },
    )
    assert invalid_captcha_response.status_code == 401
    assert (
        invalid_captcha_response.json()["detail"]["captcha_reason"] == "captcha_invalid"
    )


def test_login_success_with_captcha_resets_failed_count(
    auth_client: TestClient,
) -> None:
    auth_client.post(
        "/api/auth/register",
        json={
            "username": "gina",
            "email": "gina@example.com",
            "password": "StrongP@ss1",
        },
    )

    auth_client.post(
        "/api/auth/login",
        json={"account": "gina", "password": "wrongpass"},
    )
    auth_client.post(
        "/api/auth/login",
        json={"account": "gina", "password": "wrongpass"},
    )

    captcha_response = auth_client.get("/api/auth/captcha")
    captcha_payload = captcha_response.json()

    login_response = auth_client.post(
        "/api/auth/login",
        json={
            "account": "gina",
            "password": "StrongP@ss1",
            "captcha_id": captcha_payload["captcha_id"],
            "captcha_code": "ABCD",
        },
    )
    assert login_response.status_code == 200

    login_after_success = auth_client.post(
        "/api/auth/login",
        json={"account": "gina", "password": "wrongpass"},
    )
    assert login_after_success.status_code == 401
    assert login_after_success.json()["detail"] == "invalid credentials"
