import hashlib
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.auth import (
    get_email_sender,
    get_email_verification_store,
    get_current_user,
    get_login_challenge_store,
    get_token_store,
)
from app.cache.email_verification_store import EmailVerificationStore
from app.cache.login_challenge_store import LoginChallengeStore
from app.cache.token_store import TokenStore
from app.core.logging import get_logger
from app.core.settings import get_settings
from app.db.session import get_db_session
from app.models.user import User
from app.schemas.auth import (
    CaptchaChallengeResponse,
    ChangePasswordRequest,
    EmailCodeSendResponse,
    LoginRequest,
    MessageResponse,
    RegisterEmailCodeRequest,
    ResetPasswordEmailCodeRequest,
    ResetPasswordRequest,
    RefreshTokenRequest,
    RegisterRequest,
    TokenPairResponse,
    UserResponse,
)
from app.services.captcha_service import generate_captcha_challenge
from app.services.auth_service import (
    AuthError,
    authenticate_user,
    change_password,
    get_user_by_email,
    issue_token_pair,
    logout,
    refresh_token_pair,
    register_user,
    reset_password_by_email,
)
from app.services.email_service import EmailSender
from app.services.email_verification_service import (
    CHANGE_PASSWORD_EMAIL_SCENE,
    REGISTER_EMAIL_SCENE,
    RESET_PASSWORD_EMAIL_SCENE,
    generate_email_verification_code,
)


router = APIRouter(prefix="/auth", tags=["auth"])
logger = get_logger("app.auth")
settings = get_settings()


def _build_login_identity_key(account: str, client_ip: str) -> str:
    # 基于账号+IP做哈希，避免在 Redis key 或日志中暴露原始登录标识。
    # 该 key 用于登录失败计数，直接影响验证码风控触发。
    normalized_account = account.strip().lower()
    raw_value = f"{normalized_account}|{client_ip}"
    return hashlib.sha256(raw_value.encode("utf-8")).hexdigest()


@router.post(
    "/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED
)
async def register(
    payload: RegisterRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    email_verification_store: Annotated[
        EmailVerificationStore, Depends(get_email_verification_store)
    ],
) -> UserResponse:
    # 注册安全边界：必须先验证邮箱验证码，再进入用户创建流程。
    # 这样可以把“邮箱所有权校验”前置，降低恶意批量注册风险。
    is_email_code_valid = (
        await email_verification_store.validate_email_verification_code(
            REGISTER_EMAIL_SCENE,
            payload.email,
            payload.email_code.strip(),
        )
    )
    if not is_email_code_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="email verification code invalid",
        )

    try:
        user = await register_user(
            session,
            username=payload.username,
            email=payload.email,
            password=payload.password,
        )
    except AuthError as exc:
        logger.warning(
            "event=auth.register.failed username=%s reason=%s",
            payload.username,
            exc.detail,
        )
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    # 关键状态收敛：注册成功后立即消费验证码，防止同验证码被重复使用。
    await email_verification_store.consume_email_verification_code(
        REGISTER_EMAIL_SCENE,
        payload.email,
    )
    logger.info("event=auth.register.success user_id=%s", user.id)
    return UserResponse.model_validate(user)


@router.post("/register/email-code", response_model=EmailCodeSendResponse)
async def send_register_email_code(
    payload: RegisterEmailCodeRequest,
    email_verification_store: Annotated[
        EmailVerificationStore, Depends(get_email_verification_store)
    ],
    email_sender: Annotated[EmailSender, Depends(get_email_sender)],
) -> EmailCodeSendResponse:
    # 先抢占冷却窗口，再发送邮件，避免并发请求绕过前端倒计时而刷接口。
    is_allowed = await email_verification_store.try_acquire_send_cooldown(
        REGISTER_EMAIL_SCENE,
        payload.email,
        settings.email_code_cooldown_seconds,
    )
    if not is_allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="email verification code send too frequent",
        )

    code = generate_email_verification_code(settings.email_code_length)
    try:
        await email_sender.send_register_verification_code(
            payload.email,
            code,
            settings.email_code_ttl_seconds,
        )
        await email_verification_store.set_email_verification_code(
            REGISTER_EMAIL_SCENE,
            payload.email,
            code,
            settings.email_code_ttl_seconds,
        )
    except RuntimeError as exc:
        # 失败回滚：邮件发送失败时释放冷却锁，避免用户被错误冷却“锁死”。
        await email_verification_store.release_send_cooldown(
            REGISTER_EMAIL_SCENE,
            payload.email,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="email service unavailable",
        ) from exc

    return EmailCodeSendResponse(
        message="email code sent",
        expires_in=settings.email_code_ttl_seconds,
        cooldown_in=settings.email_code_cooldown_seconds,
    )


@router.post("/login", response_model=TokenPairResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    token_store: Annotated[TokenStore, Depends(get_token_store)],
    login_challenge_store: Annotated[
        LoginChallengeStore, Depends(get_login_challenge_store)
    ],
) -> TokenPairResponse:
    client_ip = request.client.host if request.client else "unknown"
    identity_key = _build_login_identity_key(payload.account, client_ip)
    failed_login_count = await login_challenge_store.get_failed_login_count(
        identity_key
    )

    # 风控分支：失败次数达到阈值后，必须先通过验证码，防止撞库持续尝试。
    if failed_login_count >= settings.login_captcha_threshold:
        if not payload.captcha_id or not payload.captcha_code:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "message": "captcha required",
                    "captcha_required": True,
                    "captcha_reason": "captcha_missing",
                },
            )

        is_captcha_valid = await login_challenge_store.validate_captcha_challenge(
            payload.captcha_id,
            payload.captcha_code.strip().upper(),
        )
        if not is_captcha_valid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "message": "captcha invalid",
                    "captcha_required": True,
                    "captcha_reason": "captcha_invalid",
                },
            )

    try:
        user = await authenticate_user(session, payload.account, payload.password)
        tokens = await issue_token_pair(user, token_store)
    except AuthError as exc:
        # 鉴权失败时累计失败次数；达到阈值后，响应中显式通知前端拉起验证码流程。
        current_count = await login_challenge_store.record_failed_login(
            identity_key,
            settings.login_fail_window_seconds,
        )
        logger.warning(
            "event=auth.login.failed account=%s reason=%s", payload.account, exc.detail
        )
        if current_count >= settings.login_captcha_threshold:
            raise HTTPException(
                status_code=exc.status_code,
                detail={
                    "message": exc.detail,
                    "captcha_required": True,
                    "captcha_reason": "threshold_reached",
                },
            ) from exc

        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    # 成功登录后清理风控状态，避免后续正常登录被历史失败次数误伤。
    await login_challenge_store.reset_failed_login_count(identity_key)
    if payload.captcha_id:
        await login_challenge_store.revoke_captcha_challenge(payload.captcha_id)

    logger.info("event=auth.login.success user_id=%s", user.id)
    return TokenPairResponse(**tokens)


@router.get("/captcha", response_model=CaptchaChallengeResponse)
async def get_captcha_challenge(
    login_challenge_store: Annotated[
        LoginChallengeStore, Depends(get_login_challenge_store)
    ],
) -> CaptchaChallengeResponse:
    # 验证码答案仅存储在服务端缓存，前端只拿图片与挑战 ID。
    # 这样可以避免把答案或可逆信息暴露给客户端。
    challenge = generate_captcha_challenge(settings.captcha_length)
    await login_challenge_store.set_captcha_challenge(
        challenge.captcha_id,
        challenge.answer,
        settings.captcha_ttl_seconds,
    )
    return CaptchaChallengeResponse(
        captcha_id=challenge.captcha_id,
        image_base64=challenge.image_base64,
        expires_in=settings.captcha_ttl_seconds,
    )


@router.post("/refresh", response_model=TokenPairResponse)
async def refresh(
    payload: RefreshTokenRequest,
    token_store: Annotated[TokenStore, Depends(get_token_store)],
) -> TokenPairResponse:
    try:
        tokens = await refresh_token_pair(payload.refresh_token, token_store)
    except AuthError as exc:
        logger.warning("event=auth.refresh.failed reason=%s", exc.detail)
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    logger.info("event=auth.refresh.success")
    return TokenPairResponse(**tokens)


@router.post("/change-password", response_model=MessageResponse)
async def update_password(
    payload: ChangePasswordRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    email_verification_store: Annotated[
        EmailVerificationStore, Depends(get_email_verification_store)
    ],
    email_sender: Annotated[EmailSender, Depends(get_email_sender)],
) -> MessageResponse:
    # 已登录改密仍要求邮箱验证码，形成“登录态 + 当前密码 + 邮箱所有权”三重校验。
    is_email_code_valid = (
        await email_verification_store.validate_email_verification_code(
            CHANGE_PASSWORD_EMAIL_SCENE,
            current_user.email,
            payload.email_code.strip(),
        )
    )
    if not is_email_code_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="email verification code invalid",
        )

    try:
        await change_password(
            session,
            user_id=current_user.id,
            current_password=payload.current_password,
            new_password=payload.new_password,
        )
    except AuthError as exc:
        logger.warning(
            "event=auth.password_change.failed user_id=%s reason=%s",
            current_user.id,
            exc.detail,
        )
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    # 改密成功后消费验证码，阻断验证码重放。
    await email_verification_store.consume_email_verification_code(
        CHANGE_PASSWORD_EMAIL_SCENE,
        current_user.email,
    )
    try:
        await email_sender.send_password_changed_notice(current_user.email)
    except RuntimeError:
        # 通知邮件失败不应影响主流程结果，避免“密码已改但接口报错”的一致性问题。
        logger.warning(
            "event=auth.password_change.notice_failed user_id=%s reason=email_service_unavailable",
            current_user.id,
        )

    logger.info("event=auth.password_change.success user_id=%s", current_user.id)
    return MessageResponse(message="password changed")


@router.post("/change-password/email-code", response_model=EmailCodeSendResponse)
async def send_change_password_email_code(
    current_user: Annotated[User, Depends(get_current_user)],
    email_verification_store: Annotated[
        EmailVerificationStore, Depends(get_email_verification_store)
    ],
    email_sender: Annotated[EmailSender, Depends(get_email_sender)],
) -> EmailCodeSendResponse:
    # 改密验证码同样受冷却限制，防止恶意频繁触发邮件。
    is_allowed = await email_verification_store.try_acquire_send_cooldown(
        CHANGE_PASSWORD_EMAIL_SCENE,
        current_user.email,
        settings.email_code_cooldown_seconds,
    )
    if not is_allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="email verification code send too frequent",
        )

    code = generate_email_verification_code(settings.email_code_length)
    try:
        await email_sender.send_change_password_verification_code(
            current_user.email,
            code,
            settings.email_code_ttl_seconds,
        )
        await email_verification_store.set_email_verification_code(
            CHANGE_PASSWORD_EMAIL_SCENE,
            current_user.email,
            code,
            settings.email_code_ttl_seconds,
        )
    except RuntimeError as exc:
        # 发送失败回滚冷却，避免用户必须等待冷却后才能重试。
        await email_verification_store.release_send_cooldown(
            CHANGE_PASSWORD_EMAIL_SCENE,
            current_user.email,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="email service unavailable",
        ) from exc

    return EmailCodeSendResponse(
        message="email code sent",
        expires_in=settings.email_code_ttl_seconds,
        cooldown_in=settings.email_code_cooldown_seconds,
    )


@router.post("/reset-password/email-code", response_model=EmailCodeSendResponse)
async def send_reset_password_email_code(
    payload: ResetPasswordEmailCodeRequest,
    email_verification_store: Annotated[
        EmailVerificationStore, Depends(get_email_verification_store)
    ],
    email_sender: Annotated[EmailSender, Depends(get_email_sender)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> EmailCodeSendResponse:
    # 忘记密码场景也要做发送冷却，避免接口被刷。
    is_allowed = await email_verification_store.try_acquire_send_cooldown(
        RESET_PASSWORD_EMAIL_SCENE,
        payload.email,
        settings.email_code_cooldown_seconds,
    )
    if not is_allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="email verification code send too frequent",
        )

    user = await get_user_by_email(session, payload.email)
    if user is None:
        # 防枚举策略：邮箱不存在时返回与成功一致的响应，不暴露账号存在性。
        return EmailCodeSendResponse(
            message="email code sent",
            expires_in=settings.email_code_ttl_seconds,
            cooldown_in=settings.email_code_cooldown_seconds,
        )

    code = generate_email_verification_code(settings.email_code_length)
    try:
        await email_sender.send_reset_password_verification_code(
            payload.email,
            code,
            settings.email_code_ttl_seconds,
        )
        await email_verification_store.set_email_verification_code(
            RESET_PASSWORD_EMAIL_SCENE,
            payload.email,
            code,
            settings.email_code_ttl_seconds,
        )
    except RuntimeError as exc:
        # 发送失败时释放冷却，保障用户可立即重试。
        await email_verification_store.release_send_cooldown(
            RESET_PASSWORD_EMAIL_SCENE,
            payload.email,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="email service unavailable",
        ) from exc

    return EmailCodeSendResponse(
        message="email code sent",
        expires_in=settings.email_code_ttl_seconds,
        cooldown_in=settings.email_code_cooldown_seconds,
    )


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(
    payload: ResetPasswordRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    email_verification_store: Annotated[
        EmailVerificationStore, Depends(get_email_verification_store)
    ],
    email_sender: Annotated[EmailSender, Depends(get_email_sender)],
) -> MessageResponse:
    # 未登录重置密码的安全边界：必须通过邮箱验证码校验。
    is_email_code_valid = (
        await email_verification_store.validate_email_verification_code(
            RESET_PASSWORD_EMAIL_SCENE,
            payload.email,
            payload.email_code.strip(),
        )
    )
    if not is_email_code_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="email verification code invalid",
        )

    try:
        await reset_password_by_email(
            session,
            payload.email,
            payload.new_password,
        )
    except AuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    # 重置成功后消费验证码，防止同验证码重复改密。
    await email_verification_store.consume_email_verification_code(
        RESET_PASSWORD_EMAIL_SCENE,
        payload.email,
    )
    try:
        await email_sender.send_password_changed_notice(payload.email)
    except RuntimeError:
        # 通知邮件失败不回滚已完成的密码重置，保持主事务结果稳定。
        logger.warning(
            "event=auth.password_reset.notice_failed email=%s reason=email_service_unavailable",
            payload.email,
        )

    logger.info("event=auth.password_reset.success email=%s", payload.email)
    return MessageResponse(message="password reset")


@router.post("/logout", response_model=MessageResponse)
async def do_logout(
    payload: RefreshTokenRequest,
    token_store: Annotated[TokenStore, Depends(get_token_store)],
) -> MessageResponse:
    try:
        await logout(payload.refresh_token, token_store)
    except AuthError as exc:
        logger.warning("event=auth.logout.failed reason=%s", exc.detail)
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    logger.info("event=auth.logout.success")
    return MessageResponse(message="logged out")


@router.get("/me", response_model=UserResponse)
async def me(current_user: Annotated[User, Depends(get_current_user)]) -> UserResponse:
    return UserResponse.model_validate(current_user)
