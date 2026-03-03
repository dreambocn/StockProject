import base64
import io

from PIL import Image

from app.services.captcha_service import _render_captcha_png, generate_captcha_challenge


def test_generate_captcha_challenge_returns_png_and_answer() -> None:
    challenge = generate_captcha_challenge(length=4)

    assert len(challenge.captcha_id) >= 16
    assert len(challenge.answer) == 4
    assert challenge.answer.isalnum()

    decoded = base64.b64decode(challenge.image_base64)
    assert decoded.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(decoded) > 100


def test_captcha_text_is_not_clustered_only_in_top_left(monkeypatch) -> None:
    monkeypatch.setattr("app.services.captcha_service.secrets.randbelow", lambda _: 0)

    image_bytes = _render_captcha_png("ABCD")
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")

    width, height = image.size
    right_half_dark_pixels = 0
    for x in range(width // 2, width):
        for y in range(height):
            r, g, b = image.getpixel((x, y))
            if r < 120 and g < 120 and b < 120:
                right_half_dark_pixels += 1

    assert right_half_dark_pixels > 40
