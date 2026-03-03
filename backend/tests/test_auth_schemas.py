from app.schemas.auth import CaptchaChallengeResponse, LoginRequest


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
