from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache.login_challenge_store import LoginChallengeStore
from app.cache.redis import (
    RedisLoginChallengeStore,
    RedisTokenStore,
    get_redis_client,
)
from app.cache.token_store import TokenStore
from app.core.security import TokenError, decode_token
from app.db.session import get_db_session
from app.models.user import User
from app.services.auth_service import get_user_by_id


http_bearer = HTTPBearer(auto_error=True)


def get_token_store() -> TokenStore:
    return RedisTokenStore(get_redis_client())


def get_login_challenge_store() -> LoginChallengeStore:
    return RedisLoginChallengeStore(get_redis_client())


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(http_bearer)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> User:
    token = credentials.credentials
    try:
        payload = decode_token(token, expected_type="access")
    except TokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid access token",
        ) from exc

    user_id = str(payload["sub"])
    user = await get_user_by_id(session, user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="user not found or inactive",
        )

    return user
