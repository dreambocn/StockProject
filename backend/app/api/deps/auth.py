from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache.email_verification_store import EmailVerificationStore
from app.cache.login_challenge_store import LoginChallengeStore
from app.cache.redis import (
    RedisEmailVerificationStore,
    RedisLoginChallengeStore,
    RedisTokenStore,
    get_redis_client,
)
from app.cache.token_store import TokenStore
from app.core.security import TokenError, decode_token
from app.core.settings import get_settings
from app.db.session import get_db_session
from app.models.user import USER_LEVEL_ADMIN, User
from app.services.auth_service import get_user_by_id
from app.services.email_service import EmailSender
from app.services.smtp_email_sender import SmtpEmailSender


# 统一使用 Bearer 头解析；auto_error=True 时缺失凭据会直接返回 401。
http_bearer = HTTPBearer(auto_error=True)
settings = get_settings()


def get_token_store() -> TokenStore:
    # 通过依赖注入统一令牌存储实现，便于后续替换或测试覆盖。
    return RedisTokenStore(get_redis_client())


def get_login_challenge_store() -> LoginChallengeStore:
    # 登录风控与验证码挑战统一走缓存层，保证多实例下行为一致。
    return RedisLoginChallengeStore(get_redis_client())


def get_email_verification_store() -> EmailVerificationStore:
    # 邮箱验证码的读写统一从依赖注入获取，避免路由层直接耦合 Redis 细节。
    return RedisEmailVerificationStore(get_redis_client())


def get_email_sender() -> EmailSender:
    # 邮件发送实现在依赖层收口，后续可平滑切换第三方邮件服务。
    return SmtpEmailSender(settings)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(http_bearer)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> User:
    # 认证边界：只接受 access token，refresh token 不允许访问业务接口。
    token = credentials.credentials
    try:
        payload = decode_token(token, expected_type="access")
    except TokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid access token",
        ) from exc

    # 必须回库校验用户状态，避免仅凭 token 继续访问已禁用账号。
    user_id = str(payload["sub"])
    user = await get_user_by_id(session, user_id)
    if user is None or not user.is_active:
        # 用户不存在或已禁用时统一拒绝，避免泄露具体状态给客户端。
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="user not found or inactive",
        )

    return user


async def get_current_admin(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    # 鉴权安全边界：后台管理接口必须是管理员，普通用户统一返回 403。
    if current_user.user_level != USER_LEVEL_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="insufficient permissions",
        )

    return current_user
