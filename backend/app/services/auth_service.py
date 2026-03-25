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
from app.models.user import USER_LEVEL_USER, User


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
    # 登录同时支持用户名和邮箱，统一在服务层收口查询逻辑。
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
    user_level: str = USER_LEVEL_USER,
) -> User:
    # 先校验唯一性再创建，避免数据库约束错误直接暴露给上层。
    statement = select(User).where(or_(User.username == username, User.email == email))
    result = await session.execute(statement)
    existed = result.scalar_one_or_none()
    if existed:
        raise ConflictError("username or email already exists")

    user = User(
        username=username,
        email=email,
        password_hash=hash_password(password),
        user_level=user_level,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def authenticate_user(session: AsyncSession, account: str, password: str) -> User:
    # 认证失败统一返回“invalid credentials”，减少对攻击者的账号探测信息泄露。
    user = await get_user_by_account(session, account)
    if user is None or not verify_password(password, user.password_hash):
        raise UnauthorizedError("invalid credentials")

    if not user.is_active:
        raise UnauthorizedError("inactive user")

    # 登录成功时更新最后登录时间，作为审计和安全分析依据。
    user.last_login_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(user)
    return user


async def issue_token_pair(user: User, token_store: TokenStore) -> dict[str, str]:
    # 访问令牌短期有效；刷新令牌必须落缓存，后续可撤销。
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
        # 解析时强制期待 refresh token，避免 access token 被误用。
        payload = decode_token(refresh_token, expected_type="refresh")
    except TokenError as exc:
        raise UnauthorizedError("invalid refresh token") from exc

    user_id = str(payload["sub"])
    jti = str(payload["jti"])
    # 校验 refresh token 是否仍有效，避免已撤销凭据继续刷新。
    if not await token_store.validate_refresh_token(jti, user_id):
        raise UnauthorizedError("refresh token revoked")

    # 旋转策略：先撤销旧 refresh token，再签发新 token，降低被窃取后的可用窗口。
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
    token_store: TokenStore,
) -> None:
    user = await get_user_by_id(session, user_id)
    if user is None:
        raise NotFoundError("user not found")

    if not verify_password(current_password, user.password_hash):
        raise UnauthorizedError("current password is incorrect")

    # 服务层只负责密码哈希更新，验证码与鉴权边界由路由层先行校验。
    user.password_hash = hash_password(new_password)
    await session.commit()

    # 安全关键流程：密码变更后撤销该用户所有 refresh token。
    # 这样历史会话无法继续换发新 access token，降低凭据泄露后的持续风险。
    await token_store.revoke_all_refresh_tokens_for_user(user.id)


async def logout(refresh_token: str, token_store: TokenStore) -> None:
    try:
        payload = decode_token(refresh_token, expected_type="refresh")
    except TokenError as exc:
        raise UnauthorizedError("invalid refresh token") from exc

    jti = str(payload["jti"])
    # 登出语义是撤销 refresh token，后续刷新流程将被拒绝。
    await token_store.revoke_refresh_token(jti)


async def reset_password_by_email(
    session: AsyncSession,
    email: str,
    new_password: str,
    token_store: TokenStore,
) -> None:
    user = await get_user_by_email(session, email)
    if user is None:
        raise NotFoundError("user not found")

    # 找回密码流程不改变账号状态，只更新密码并回收刷新令牌。
    # 忘记密码链路只更新目标用户密码，邮箱验证码校验由上层完成。
    user.password_hash = hash_password(new_password)
    await session.commit()

    # 安全关键流程：找回密码成功后全量撤销 refresh token。
    # access token 保持“到期即失效”策略，避免引入额外的全局会话状态耦合。
    await token_store.revoke_all_refresh_tokens_for_user(user.id)
