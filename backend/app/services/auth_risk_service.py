import hashlib
from collections.abc import Sequence
from typing import Protocol


EMAIL_CODE_RISK_LIMIT_DETAIL = "email verification code send too frequent"


class EmailVerificationRiskStore(Protocol):
    async def is_ip_blocked(self, ip: str) -> bool: ...

    async def check_and_increment_ip_limits(
        self,
        scene: str,
        ip: str,
        per_minute: int,
        per_day: int,
        block_seconds: int,
    ) -> bool: ...


class EmailCodeRiskControlError(Exception):
    pass


def build_login_identity_key(account: str, client_ip: str) -> str:
    # 基于账号+IP做哈希，避免在 Redis key 或日志中暴露原始登录标识。
    # 该 key 直接用于失败计数，属于风控边界的关键索引。
    normalized_account = account.strip().lower()
    raw_value = f"{normalized_account}|{client_ip}"
    return hashlib.sha256(raw_value.encode("utf-8")).hexdigest()


def resolve_client_ip(
    *,
    direct_client_ip: str,
    forwarded_for: str,
    trust_proxy_headers: bool,
    trusted_proxy_ips: Sequence[str],
) -> str:
    # 仅在“显式信任代理 + 来源是受信代理”时读取 X-Forwarded-For，
    # 避免客户端伪造头部绕过 IP 风控。
    if not trust_proxy_headers:
        return direct_client_ip
    if not trusted_proxy_ips:
        return direct_client_ip
    if direct_client_ip not in trusted_proxy_ips:
        return direct_client_ip

    forwarded_ip = forwarded_for.split(",", 1)[0].strip()
    if not forwarded_ip:
        return direct_client_ip

    return forwarded_ip


async def enforce_email_code_ip_risk_control(
    *,
    scene: str,
    client_ip: str,
    email_verification_store: EmailVerificationRiskStore,
    per_minute_limit: int,
    per_day_limit: int,
    block_seconds: int,
) -> None:
    # 关键流程：先黑名单，再计数限流。命中任一分支都要立即失败，
    # 防止高风险请求继续进入发送冷却与发信路径。
    if await email_verification_store.is_ip_blocked(client_ip):
        raise EmailCodeRiskControlError(EMAIL_CODE_RISK_LIMIT_DETAIL)

    is_allowed = await email_verification_store.check_and_increment_ip_limits(
        scene,
        client_ip,
        per_minute_limit,
        per_day_limit,
        block_seconds,
    )
    if not is_allowed:
        raise EmailCodeRiskControlError(EMAIL_CODE_RISK_LIMIT_DETAIL)
