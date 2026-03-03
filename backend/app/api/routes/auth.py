import hashlib
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.auth import (
    get_current_user,
    get_login_challenge_store,
    get_token_store,
)
from app.cache.login_challenge_store import LoginChallengeStore
from app.cache.token_store import TokenStore
from app.core.logging import get_logger
from app.core.settings import get_settings
from app.db.session import get_db_session
from app.models.user import User
from app.schemas.auth import (
    CaptchaChallengeResponse,
    ChangePasswordRequest,
    LoginRequest,
    MessageResponse,
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
    issue_token_pair,
    logout,
    refresh_token_pair,
    register_user,
)


router = APIRouter(prefix="/auth", tags=["auth"])
logger = get_logger("app.auth")
settings = get_settings()


def _build_login_identity_key(account: str, client_ip: str) -> str:
    normalized_account = account.strip().lower()
    raw_value = f"{normalized_account}|{client_ip}"
    return hashlib.sha256(raw_value.encode("utf-8")).hexdigest()


@router.post(
    "/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED
)
async def register(
    payload: RegisterRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> UserResponse:
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

    logger.info("event=auth.register.success user_id=%s", user.id)
    return UserResponse.model_validate(user)


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
) -> MessageResponse:
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

    logger.info("event=auth.password_change.success user_id=%s", current_user.id)
    return MessageResponse(message="password changed")


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
