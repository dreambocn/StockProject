import asyncio

import pytest

from app.services.auth_risk_service import (
    EmailCodeRiskControlError,
    build_login_identity_key,
    enforce_email_code_ip_risk_control,
    resolve_client_ip,
)


class FakeEmailVerificationStore:
    def __init__(self, *, blocked: bool, allow_increment: bool) -> None:
        self.blocked = blocked
        self.allow_increment = allow_increment
        self.increment_calls: list[tuple[str, str, int, int, int]] = []

    async def is_ip_blocked(self, ip: str) -> bool:
        _ = ip
        return self.blocked

    async def check_and_increment_ip_limits(
        self,
        scene: str,
        ip: str,
        per_minute: int,
        per_day: int,
        block_seconds: int,
    ) -> bool:
        self.increment_calls.append((scene, ip, per_minute, per_day, block_seconds))
        return self.allow_increment


def test_build_login_identity_key_normalizes_account() -> None:
    key_with_spaces = build_login_identity_key(" Alice@Example.com ", "127.0.0.1")
    key_normalized = build_login_identity_key("alice@example.com", "127.0.0.1")

    assert key_with_spaces == key_normalized


def test_resolve_client_ip_returns_direct_when_proxy_not_trusted() -> None:
    ip = resolve_client_ip(
        direct_client_ip="10.0.0.1",
        forwarded_for="203.0.113.7",
        trust_proxy_headers=False,
        trusted_proxy_ips=["10.0.0.1"],
    )

    assert ip == "10.0.0.1"


def test_resolve_client_ip_uses_forwarded_for_when_proxy_trusted() -> None:
    ip = resolve_client_ip(
        direct_client_ip="10.0.0.1",
        forwarded_for="203.0.113.7, 203.0.113.8",
        trust_proxy_headers=True,
        trusted_proxy_ips=["10.0.0.1"],
    )

    assert ip == "203.0.113.7"


def test_enforce_email_code_ip_risk_control_rejects_blocked_ip() -> None:
    store = FakeEmailVerificationStore(blocked=True, allow_increment=True)

    async def _run() -> None:
        with pytest.raises(EmailCodeRiskControlError) as exc_info:
            await enforce_email_code_ip_risk_control(
                scene="register",
                client_ip="198.51.100.1",
                email_verification_store=store,
                per_minute_limit=10,
                per_day_limit=200,
                block_seconds=900,
            )

        assert str(exc_info.value) == "email verification code send too frequent"
        assert store.increment_calls == []

    asyncio.run(_run())


def test_enforce_email_code_ip_risk_control_rejects_limit_exceeded() -> None:
    store = FakeEmailVerificationStore(blocked=False, allow_increment=False)

    async def _run() -> None:
        with pytest.raises(EmailCodeRiskControlError) as exc_info:
            await enforce_email_code_ip_risk_control(
                scene="register",
                client_ip="198.51.100.1",
                email_verification_store=store,
                per_minute_limit=10,
                per_day_limit=200,
                block_seconds=900,
            )

        assert str(exc_info.value) == "email verification code send too frequent"
        assert store.increment_calls == [("register", "198.51.100.1", 10, 200, 900)]

    asyncio.run(_run())


def test_enforce_email_code_ip_risk_control_allows_safe_request() -> None:
    store = FakeEmailVerificationStore(blocked=False, allow_increment=True)

    async def _run() -> None:
        await enforce_email_code_ip_risk_control(
            scene="register",
            client_ip="198.51.100.1",
            email_verification_store=store,
            per_minute_limit=10,
            per_day_limit=200,
            block_seconds=900,
        )

        assert store.increment_calls == [("register", "198.51.100.1", 10, 200, 900)]

    asyncio.run(_run())
