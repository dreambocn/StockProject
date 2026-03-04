from app.schemas.auth import (
    CaptchaChallengeResponse,
    ChangePasswordRequest,
    EmailCodeSendResponse,
    LoginRequest,
    RegisterRequest,
    ResetPasswordRequest,
)


def test_login_request_accepts_optional_captcha_fields() -> None:
    payload = LoginRequest(
        account="alice",
        password="Passw0rd!123",
        captcha_id="challenge-1",
        captcha_code="AB12",
    )

    assert payload.captcha_id == "challenge-1"
    assert payload.captcha_code == "AB12"


def test_captcha_challenge_response_schema() -> None:
    payload = CaptchaChallengeResponse(
        captcha_id="challenge-1",
        image_base64="ZmFrZQ==",
        expires_in=300,
    )

    assert payload.captcha_id == "challenge-1"
    assert payload.expires_in == 300


def test_register_request_requires_email_code() -> None:
    payload = RegisterRequest(
        username="alice",
        email="alice@example.com",
        email_code="123456",
        password="Passw0rd!123",
    )

    assert payload.email_code == "123456"


def test_change_password_request_requires_email_code() -> None:
    payload = ChangePasswordRequest(
        current_password="Passw0rd!123",
        new_password="N3wPass!456",
        email_code="123456",
    )

    assert payload.email_code == "123456"


def test_email_code_send_response_schema() -> None:
    payload = EmailCodeSendResponse(
        message="email code sent",
        expires_in=300,
        cooldown_in=60,
    )

    assert payload.message == "email code sent"


def test_reset_password_request_requires_email_code() -> None:
    payload = ResetPasswordRequest(
        email="alice@example.com",
        email_code="123456",
        new_password="N3wPass!456",
    )

    assert payload.email_code == "123456"
