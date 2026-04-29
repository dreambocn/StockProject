import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from conftest import build_sqlite_test_context, init_sqlite_schema

from app.api.deps.auth import (
    get_email_sender,
    get_email_verification_store,
    get_login_challenge_store,
    get_token_store,
)
from app.cache.redis import AuthCacheUnavailableError
from app.db.base import Base
from app.db.session import get_db_session
from app.main import app


class InMemoryTokenStore:
    def __init__(self) -> None:
        self._store: dict[str, str] = {}
        self._user_index: dict[str, set[str]] = {}

    async def set_refresh_token(
        self, jti: str, user_id: str, expires_seconds: int
    ) -> None:
        self._store[jti] = user_id
        if user_id not in self._user_index:
            self._user_index[user_id] = set()
        self._user_index[user_id].add(jti)

    async def validate_refresh_token(self, jti: str, user_id: str) -> bool:
        return self._store.get(jti) == user_id

    async def revoke_refresh_token(self, jti: str) -> None:
        user_id = self._store.pop(jti, None)
        if user_id is None:
            return

        user_jtis = self._user_index.get(user_id)
        if user_jtis is None:
            return

        user_jtis.discard(jti)
        if not user_jtis:
            self._user_index.pop(user_id, None)

    async def revoke_all_refresh_tokens_for_user(self, user_id: str) -> None:
        user_jtis = self._user_index.pop(user_id, set())
        for jti in user_jtis:
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


class InMemoryEmailVerificationStore:
    def __init__(self) -> None:
        self.codes: dict[tuple[str, str], str] = {}
        self.cooldowns: set[tuple[str, str]] = set()
        self.ip_minute_counts: dict[tuple[str, str], int] = {}
        self.ip_day_counts: dict[tuple[str, str], int] = {}
        self.blocked_ips: set[str] = set()

    def _key(self, scene: str, email: str) -> tuple[str, str]:
        return (scene, email.strip().lower())

    def _ip_key(self, scene: str, ip: str) -> tuple[str, str]:
        return (scene, ip.strip().lower())

    async def try_acquire_send_cooldown(
        self, scene: str, email: str, cooldown_seconds: int
    ) -> bool:
        key = self._key(scene, email)
        if key in self.cooldowns:
            return False
        self.cooldowns.add(key)
        return True

    async def release_send_cooldown(self, scene: str, email: str) -> None:
        self.cooldowns.discard(self._key(scene, email))

    async def set_email_verification_code(
        self, scene: str, email: str, code: str, expires_seconds: int
    ) -> None:
        self.codes[self._key(scene, email)] = "000000"

    async def validate_email_verification_code(
        self, scene: str, email: str, code: str
    ) -> bool:
        return self.codes.get(self._key(scene, email)) == code

    async def consume_email_verification_code(self, scene: str, email: str) -> None:
        self.codes.pop(self._key(scene, email), None)

    async def is_ip_blocked(self, ip: str) -> bool:
        return ip.strip().lower() in self.blocked_ips

    async def check_and_increment_ip_limits(
        self,
        scene: str,
        ip: str,
        minute_limit: int,
        day_limit: int,
        block_seconds: int,
    ) -> bool:
        ip_key = self._ip_key(scene, ip)

        minute_count = self.ip_minute_counts.get(ip_key, 0) + 1
        day_count = self.ip_day_counts.get(ip_key, 0) + 1
        self.ip_minute_counts[ip_key] = minute_count
        self.ip_day_counts[ip_key] = day_count

        if minute_count > minute_limit or day_count > day_limit:
            self.blocked_ips.add(ip.strip().lower())
            return False

        return True


class InMemoryEmailSender:
    def __init__(self) -> None:
        self.sent_verification: list[tuple[str, str, str, int]] = []
        self.sent_notices: list[str] = []

    async def send_register_verification_code(
        self, email: str, code: str, expires_seconds: int
    ) -> None:
        self.sent_verification.append(("register", email, code, expires_seconds))

    async def send_change_password_verification_code(
        self, email: str, code: str, expires_seconds: int
    ) -> None:
        self.sent_verification.append(("change_password", email, code, expires_seconds))

    async def send_reset_password_verification_code(
        self, email: str, code: str, expires_seconds: int
    ) -> None:
        self.sent_verification.append(("reset_password", email, code, expires_seconds))

    async def send_password_changed_notice(self, email: str) -> None:
        self.sent_notices.append(email)


class BrokenLoginChallengeStore:
    async def record_failed_login(self, identity_key: str, window_seconds: int) -> int:
        _ = identity_key, window_seconds
        raise AuthCacheUnavailableError("auth service unavailable")

    async def get_failed_login_count(self, identity_key: str) -> int:
        _ = identity_key
        raise AuthCacheUnavailableError("auth service unavailable")

    async def reset_failed_login_count(self, identity_key: str) -> None:
        _ = identity_key
        raise AuthCacheUnavailableError("auth service unavailable")

    async def set_captcha_challenge(
        self, captcha_id: str, answer: str, expires_seconds: int
    ) -> None:
        _ = captcha_id, answer, expires_seconds
        raise AuthCacheUnavailableError("auth service unavailable")

    async def validate_captcha_challenge(self, captcha_id: str, answer: str) -> bool:
        _ = captcha_id, answer
        raise AuthCacheUnavailableError("auth service unavailable")

    async def revoke_captcha_challenge(self, captcha_id: str) -> None:
        _ = captcha_id
        raise AuthCacheUnavailableError("auth service unavailable")


class BrokenTokenStore:
    async def set_refresh_token(
        self, jti: str, user_id: str, expires_seconds: int
    ) -> None:
        _ = jti, user_id, expires_seconds
        raise AuthCacheUnavailableError("auth service unavailable")

    async def validate_refresh_token(self, jti: str, user_id: str) -> bool:
        _ = jti, user_id
        raise AuthCacheUnavailableError("auth service unavailable")

    async def revoke_refresh_token(self, jti: str) -> None:
        _ = jti
        raise AuthCacheUnavailableError("auth service unavailable")

    async def revoke_all_refresh_tokens_for_user(self, user_id: str) -> None:
        _ = user_id
        raise AuthCacheUnavailableError("auth service unavailable")


class BrokenEmailVerificationStore:
    async def try_acquire_send_cooldown(
        self, scene: str, email: str, cooldown_seconds: int
    ) -> bool:
        _ = scene, email, cooldown_seconds
        raise AuthCacheUnavailableError("auth service unavailable")

    async def release_send_cooldown(self, scene: str, email: str) -> None:
        _ = scene, email
        raise AuthCacheUnavailableError("auth service unavailable")

    async def set_email_verification_code(
        self, scene: str, email: str, code: str, expires_seconds: int
    ) -> None:
        _ = scene, email, code, expires_seconds
        raise AuthCacheUnavailableError("auth service unavailable")

    async def validate_email_verification_code(
        self, scene: str, email: str, code: str
    ) -> bool:
        _ = scene, email, code
        raise AuthCacheUnavailableError("auth service unavailable")

    async def consume_email_verification_code(self, scene: str, email: str) -> None:
        _ = scene, email
        raise AuthCacheUnavailableError("auth service unavailable")

    async def is_ip_blocked(self, ip: str) -> bool:
        _ = ip
        raise AuthCacheUnavailableError("auth service unavailable")

    async def check_and_increment_ip_limits(
        self,
        scene: str,
        ip: str,
        minute_limit: int,
        day_limit: int,
        block_seconds: int,
    ) -> bool:
        _ = scene, ip, minute_limit, day_limit, block_seconds
        raise AuthCacheUnavailableError("auth service unavailable")


@pytest.fixture
def auth_client(tmp_path: Path) -> TestClient:
    engine, test_session_maker = build_sqlite_test_context(tmp_path, "auth-test.db")
    init_sqlite_schema(engine)

    async def override_get_db_session():
        async with test_session_maker() as session:
            yield session

    token_store = InMemoryTokenStore()
    login_challenge_store = InMemoryLoginChallengeStore()
    email_verification_store = InMemoryEmailVerificationStore()
    email_sender = InMemoryEmailSender()
    app.dependency_overrides[get_db_session] = override_get_db_session
    app.dependency_overrides[get_token_store] = lambda: token_store
    app.dependency_overrides[get_login_challenge_store] = lambda: login_challenge_store
    app.dependency_overrides[get_email_verification_store] = lambda: (
        email_verification_store
    )
    app.dependency_overrides[get_email_sender] = lambda: email_sender

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()


def test_register_login_refresh_change_password_logout_flow(
    auth_client: TestClient,
) -> None:
    send_code_response = auth_client.post(
        "/api/auth/register/email-code",
        json={"email": "alice@example.com"},
    )
    assert send_code_response.status_code == 200

    register_response = auth_client.post(
        "/api/auth/register",
        json={
            "username": "alice",
            "email": "alice@example.com",
            "email_code": "000000",
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
        json={
            "current_password": "Passw0rd!123",
            "new_password": "N3wPass!456",
            "email_code": "000000",
        },
        headers={"Authorization": f"Bearer {login_payload['access_token']}"},
    )
    assert change_password_response.status_code == 400

    send_change_password_code_response = auth_client.post(
        "/api/auth/change-password/email-code",
        headers={"Authorization": f"Bearer {login_payload['access_token']}"},
    )
    assert send_change_password_code_response.status_code == 200

    change_password_response = auth_client.post(
        "/api/auth/change-password",
        json={
            "current_password": "Passw0rd!123",
            "new_password": "N3wPass!456",
            "email_code": "000000",
        },
        headers={"Authorization": f"Bearer {login_payload['access_token']}"},
    )
    assert change_password_response.status_code == 200

    refresh_after_change_password_response = auth_client.post(
        "/api/auth/refresh",
        json={"refresh_token": login_payload["refresh_token"]},
    )
    assert refresh_after_change_password_response.status_code == 401

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
    send_code_response = auth_client.post(
        "/api/auth/register/email-code",
        json={"email": "bob@example.com"},
    )
    assert send_code_response.status_code == 200

    register_response = auth_client.post(
        "/api/auth/register",
        json={
            "username": "bob",
            "email": "bob@example.com",
            "email_code": "000000",
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


def test_login_returns_503_when_login_challenge_store_unavailable(
    auth_client: TestClient,
) -> None:
    original_override = app.dependency_overrides[get_login_challenge_store]
    app.dependency_overrides[get_login_challenge_store] = lambda: BrokenLoginChallengeStore()
    try:
        response = auth_client.post(
            "/api/auth/login",
            json={"account": "alice", "password": "Passw0rd!123"},
        )
    finally:
        app.dependency_overrides[get_login_challenge_store] = original_override

    assert response.status_code == 503
    assert response.json()["detail"] == "auth service unavailable"


def test_login_returns_503_when_token_store_unavailable_after_authentication(
    auth_client: TestClient,
) -> None:
    send_code_response = auth_client.post(
        "/api/auth/register/email-code",
        json={"email": "redis-login@example.com"},
    )
    assert send_code_response.status_code == 200
    register_response = auth_client.post(
        "/api/auth/register",
        json={
            "username": "redis-login",
            "email": "redis-login@example.com",
            "email_code": "000000",
            "password": "Passw0rd!123",
        },
    )
    assert register_response.status_code == 201

    original_override = app.dependency_overrides[get_token_store]
    app.dependency_overrides[get_token_store] = lambda: BrokenTokenStore()
    try:
        response = auth_client.post(
            "/api/auth/login",
            json={"account": "redis-login", "password": "Passw0rd!123"},
        )
    finally:
        app.dependency_overrides[get_token_store] = original_override

    assert response.status_code == 503
    assert response.json()["detail"] == "auth service unavailable"


def test_register_rejects_weak_password(auth_client: TestClient) -> None:
    send_code_response = auth_client.post(
        "/api/auth/register/email-code",
        json={"email": "charlie@example.com"},
    )
    assert send_code_response.status_code == 200

    register_response = auth_client.post(
        "/api/auth/register",
        json={
            "username": "charlie",
            "email": "charlie@example.com",
            "email_code": "000000",
            "password": "weakpass",
        },
    )

    assert register_response.status_code == 422
    assert "Password" in str(register_response.json())


def test_change_password_rejects_weak_new_password(auth_client: TestClient) -> None:
    send_code_response = auth_client.post(
        "/api/auth/register/email-code",
        json={"email": "dora@example.com"},
    )
    assert send_code_response.status_code == 200

    register_response = auth_client.post(
        "/api/auth/register",
        json={
            "username": "dora",
            "email": "dora@example.com",
            "email_code": "000000",
            "password": "StrongP@ss1",
        },
    )
    assert register_response.status_code == 201

    login_response = auth_client.post(
        "/api/auth/login",
        json={"account": "dora", "password": "StrongP@ss1"},
    )
    assert login_response.status_code == 200

    send_change_password_code_response = auth_client.post(
        "/api/auth/change-password/email-code",
        headers={"Authorization": f"Bearer {login_response.json()['access_token']}"},
    )
    assert send_change_password_code_response.status_code == 200

    change_password_response = auth_client.post(
        "/api/auth/change-password",
        json={
            "current_password": "StrongP@ss1",
            "new_password": "weakpass",
            "email_code": "000000",
        },
        headers={"Authorization": f"Bearer {login_response.json()['access_token']}"},
    )

    assert change_password_response.status_code == 422
    assert "Password" in str(change_password_response.json())


def test_login_requires_captcha_after_two_failed_attempts(
    auth_client: TestClient,
) -> None:
    send_code_response = auth_client.post(
        "/api/auth/register/email-code",
        json={"email": "eve@example.com"},
    )
    assert send_code_response.status_code == 200

    register_response = auth_client.post(
        "/api/auth/register",
        json={
            "username": "eve",
            "email": "eve@example.com",
            "email_code": "000000",
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


def test_get_captcha_challenge_returns_503_when_store_unavailable(
    auth_client: TestClient,
) -> None:
    original_override = app.dependency_overrides[get_login_challenge_store]
    app.dependency_overrides[get_login_challenge_store] = lambda: BrokenLoginChallengeStore()
    try:
        response = auth_client.get("/api/auth/captcha")
    finally:
        app.dependency_overrides[get_login_challenge_store] = original_override

    assert response.status_code == 503
    assert response.json()["detail"] == "auth service unavailable"


def test_login_rejects_missing_or_invalid_captcha_after_threshold(
    auth_client: TestClient,
) -> None:
    send_code_response = auth_client.post(
        "/api/auth/register/email-code",
        json={"email": "frank@example.com"},
    )
    assert send_code_response.status_code == 200

    auth_client.post(
        "/api/auth/register",
        json={
            "username": "frank",
            "email": "frank@example.com",
            "email_code": "000000",
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
    send_code_response = auth_client.post(
        "/api/auth/register/email-code",
        json={"email": "gina@example.com"},
    )
    assert send_code_response.status_code == 200

    auth_client.post(
        "/api/auth/register",
        json={
            "username": "gina",
            "email": "gina@example.com",
            "email_code": "000000",
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


def test_register_requires_valid_email_code(auth_client: TestClient) -> None:
    missing_code_response = auth_client.post(
        "/api/auth/register",
        json={
            "username": "hank",
            "email": "hank@example.com",
            "password": "StrongP@ss1",
        },
    )
    assert missing_code_response.status_code == 422

    invalid_code_response = auth_client.post(
        "/api/auth/register",
        json={
            "username": "hank",
            "email": "hank@example.com",
            "email_code": "999999",
            "password": "StrongP@ss1",
        },
    )
    assert invalid_code_response.status_code == 400


def test_change_password_requires_valid_email_code(auth_client: TestClient) -> None:
    send_register_code_response = auth_client.post(
        "/api/auth/register/email-code",
        json={"email": "ivy@example.com"},
    )
    assert send_register_code_response.status_code == 200

    register_response = auth_client.post(
        "/api/auth/register",
        json={
            "username": "ivy",
            "email": "ivy@example.com",
            "email_code": "000000",
            "password": "StrongP@ss1",
        },
    )
    assert register_response.status_code == 201

    login_response = auth_client.post(
        "/api/auth/login",
        json={"account": "ivy", "password": "StrongP@ss1"},
    )
    assert login_response.status_code == 200
    access_token = login_response.json()["access_token"]

    no_code_response = auth_client.post(
        "/api/auth/change-password",
        json={
            "current_password": "StrongP@ss1",
            "new_password": "N3wPass!456",
        },
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert no_code_response.status_code == 422

    invalid_code_response = auth_client.post(
        "/api/auth/change-password",
        json={
            "current_password": "StrongP@ss1",
            "new_password": "N3wPass!456",
            "email_code": "999999",
        },
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert invalid_code_response.status_code == 400


def test_email_code_send_endpoint_has_cooldown(auth_client: TestClient) -> None:
    first_send_response = auth_client.post(
        "/api/auth/register/email-code",
        json={"email": "jack@example.com"},
    )
    second_send_response = auth_client.post(
        "/api/auth/register/email-code",
        json={"email": "jack@example.com"},
    )

    assert first_send_response.status_code == 200
    assert second_send_response.status_code == 429


def test_register_email_code_returns_503_when_store_unavailable(
    auth_client: TestClient,
) -> None:
    original_override = app.dependency_overrides[get_email_verification_store]
    app.dependency_overrides[get_email_verification_store] = lambda: BrokenEmailVerificationStore()
    try:
        response = auth_client.post(
            "/api/auth/register/email-code",
            json={"email": "cache-down@example.com"},
        )
    finally:
        app.dependency_overrides[get_email_verification_store] = original_override

    assert response.status_code == 503
    assert response.json()["detail"] == "auth service unavailable"


def test_reset_password_flow_with_email_code(auth_client: TestClient) -> None:
    send_register_code_response = auth_client.post(
        "/api/auth/register/email-code",
        json={"email": "kate@example.com"},
    )
    assert send_register_code_response.status_code == 200

    register_response = auth_client.post(
        "/api/auth/register",
        json={
            "username": "kate",
            "email": "kate@example.com",
            "email_code": "000000",
            "password": "StrongP@ss1",
        },
    )
    assert register_response.status_code == 201

    login_before_reset_response = auth_client.post(
        "/api/auth/login",
        json={"account": "kate", "password": "StrongP@ss1"},
    )
    assert login_before_reset_response.status_code == 200
    refresh_token_before_reset = login_before_reset_response.json()["refresh_token"]

    send_reset_code_response = auth_client.post(
        "/api/auth/reset-password/email-code",
        json={"email": "kate@example.com"},
    )
    assert send_reset_code_response.status_code == 200

    reset_response = auth_client.post(
        "/api/auth/reset-password",
        json={
            "email": "kate@example.com",
            "email_code": "000000",
            "new_password": "N3wPass!456",
        },
    )
    assert reset_response.status_code == 200

    refresh_after_reset_response = auth_client.post(
        "/api/auth/refresh",
        json={"refresh_token": refresh_token_before_reset},
    )
    assert refresh_after_reset_response.status_code == 401

    old_login_response = auth_client.post(
        "/api/auth/login",
        json={"account": "kate", "password": "StrongP@ss1"},
    )
    assert old_login_response.status_code == 401

    new_login_response = auth_client.post(
        "/api/auth/login",
        json={"account": "kate", "password": "N3wPass!456"},
    )
    assert new_login_response.status_code == 200


def test_refresh_and_logout_return_503_when_token_store_unavailable(
    auth_client: TestClient,
) -> None:
    send_code_response = auth_client.post(
        "/api/auth/register/email-code",
        json={"email": "redis-refresh@example.com"},
    )
    assert send_code_response.status_code == 200
    register_response = auth_client.post(
        "/api/auth/register",
        json={
            "username": "redis-refresh",
            "email": "redis-refresh@example.com",
            "email_code": "000000",
            "password": "Passw0rd!123",
        },
    )
    assert register_response.status_code == 201
    login_response = auth_client.post(
        "/api/auth/login",
        json={"account": "redis-refresh", "password": "Passw0rd!123"},
    )
    assert login_response.status_code == 200
    refresh_token = login_response.json()["refresh_token"]

    original_override = app.dependency_overrides[get_token_store]
    app.dependency_overrides[get_token_store] = lambda: BrokenTokenStore()
    try:
        refresh_response = auth_client.post(
            "/api/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        logout_response = auth_client.post(
            "/api/auth/logout",
            json={"refresh_token": refresh_token},
        )
    finally:
        app.dependency_overrides[get_token_store] = original_override

    assert refresh_response.status_code == 503
    assert refresh_response.json()["detail"] == "auth service unavailable"
    assert logout_response.status_code == 503
    assert logout_response.json()["detail"] == "auth service unavailable"


def test_register_email_code_ip_rate_limit_blocks_after_threshold(
    auth_client: TestClient,
) -> None:
    responses = [
        auth_client.post(
            "/api/auth/register/email-code",
            json={"email": f"limit-{index}@example.com"},
        )
        for index in range(1, 12)
    ]

    for response in responses[:10]:
        assert response.status_code == 200
    assert responses[10].status_code == 429

    email_sender = app.dependency_overrides[get_email_sender]()
    assert len(email_sender.sent_verification) == 10


def test_blocked_ip_is_rejected_on_reset_password_email_code(
    auth_client: TestClient,
) -> None:
    responses = [
        auth_client.post(
            "/api/auth/register/email-code",
            json={"email": f"block-{index}@example.com"},
        )
        for index in range(1, 12)
    ]
    blocked_reset_response = auth_client.post(
        "/api/auth/reset-password/email-code",
        json={"email": "nobody@example.com"},
    )

    for response in responses[:10]:
        assert response.status_code == 200
    assert responses[10].status_code == 429
    assert blocked_reset_response.status_code == 429

    email_sender = app.dependency_overrides[get_email_sender]()
    assert len(email_sender.sent_verification) == 10
