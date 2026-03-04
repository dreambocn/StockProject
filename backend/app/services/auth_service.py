from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache.token_store import TokenStore
from app.core.security import (
    TokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.user import User


class AuthError(Exception):
    status_code = 400

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class ConflictError(AuthError):
    status_code = 409


class UnauthorizedError(AuthError):
    status_code = 401


class NotFoundError(AuthError):
    status_code = 404


async def get_user_by_id(session: AsyncSession, user_id: str) -> User | None:
    return await session.get(User, user_id)


async def get_user_by_account(session: AsyncSession, account: str) -> User | None:
    statement = select(User).where(or_(User.email == account, User.username == account))
    result = await session.execute(statement)
    return result.scalar_one_or_none()


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    statement = select(User).where(User.email == email)
    result = await session.execute(statement)
    return result.scalar_one_or_none()


async def register_user(
    session: AsyncSession,
    username: str,
    email: str,
    password: str,
) -> User:
    statement = select(User).where(or_(User.username == username, User.email == email))
    result = await session.execute(statement)
    existed = result.scalar_one_or_none()
    if existed:
        raise ConflictError("username or email already exists")

    user = User(username=username, email=email, password_hash=hash_password(password))
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def authenticate_user(session: AsyncSession, account: str, password: str) -> User:
    user = await get_user_by_account(session, account)
    if user is None or not verify_password(password, user.password_hash):
        raise UnauthorizedError("invalid credentials")

    if not user.is_active:
        raise UnauthorizedError("inactive user")

    user.last_login_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(user)
    return user


async def issue_token_pair(user: User, token_store: TokenStore) -> dict[str, str]:
    access_token = create_access_token(user.id)
    refresh_token, jti, expires_seconds = create_refresh_token(user.id)
    await token_store.set_refresh_token(jti, user.id, expires_seconds)
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }


async def refresh_token_pair(
    refresh_token: str, token_store: TokenStore
) -> dict[str, str]:
    try:
        payload = decode_token(refresh_token, expected_type="refresh")
    except TokenError as exc:
        raise UnauthorizedError("invalid refresh token") from exc

    user_id = str(payload["sub"])
    jti = str(payload["jti"])
    if not await token_store.validate_refresh_token(jti, user_id):
        raise UnauthorizedError("refresh token revoked")

    await token_store.revoke_refresh_token(jti)

    access_token = create_access_token(user_id)
    new_refresh_token, new_jti, expires_seconds = create_refresh_token(user_id)
    await token_store.set_refresh_token(new_jti, user_id, expires_seconds)
    return {
        "access_token": access_token,
        "refresh_token": new_refresh_token,
        "token_type": "bearer",
    }


async def change_password(
    session: AsyncSession,
    user_id: str,
    current_password: str,
    new_password: str,
) -> None:
    user = await get_user_by_id(session, user_id)
    if user is None:
        raise NotFoundError("user not found")

    if not verify_password(current_password, user.password_hash):
        raise UnauthorizedError("current password is incorrect")

    user.password_hash = hash_password(new_password)
    await session.commit()


async def logout(refresh_token: str, token_store: TokenStore) -> None:
    try:
        payload = decode_token(refresh_token, expected_type="refresh")
    except TokenError as exc:
        raise UnauthorizedError("invalid refresh token") from exc

    jti = str(payload["jti"])
    await token_store.revoke_refresh_token(jti)


async def reset_password_by_email(
    session: AsyncSession,
    email: str,
    new_password: str,
) -> None:
    user = await get_user_by_email(session, email)
    if user is None:
        raise NotFoundError("user not found")

    user.password_hash = hash_password(new_password)
    await session.commit()
