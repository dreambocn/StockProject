from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
from pwdlib import PasswordHash

from app.core.settings import get_settings


password_hasher = PasswordHash.recommended()
settings = get_settings()


class TokenError(Exception):
    pass


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return password_hasher.verify(password, password_hash)


def _create_token(
    subject: str, token_type: str, expires_seconds: int, jti: str | None = None
) -> tuple[str, str]:
    token_jti = jti or uuid4().hex
    issued_at = datetime.now(UTC)
    payload = {
        "sub": subject,
        "type": token_type,
        "jti": token_jti,
        "iat": int(issued_at.timestamp()),
        "exp": int((issued_at + timedelta(seconds=expires_seconds)).timestamp()),
    }
    token = jwt.encode(
        payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
    )
    return token, token_jti


def create_access_token(user_id: str) -> str:
    token, _ = _create_token(user_id, "access", settings.access_token_expire_seconds)
    return token


def create_refresh_token(user_id: str) -> tuple[str, str, int]:
    token, jti = _create_token(
        user_id, "refresh", settings.refresh_token_expire_seconds
    )
    return token, jti, settings.refresh_token_expire_seconds


def decode_token(token: str, expected_type: str) -> dict[str, str | int]:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.PyJWTError as exc:
        raise TokenError("invalid token") from exc

    if payload.get("type") != expected_type:
        raise TokenError("invalid token type")

    if not payload.get("sub") or not payload.get("jti"):
        raise TokenError("invalid token payload")

    return payload
