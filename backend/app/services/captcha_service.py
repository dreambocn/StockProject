import base64
import io
import secrets
import string
from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFont


@dataclass(frozen=True)
class CaptchaChallenge:
    captcha_id: str
    answer: str
    image_base64: str


def _build_answer(length: int) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _render_captcha_png(answer: str) -> bytes:
    width, height = 180, 64
    image = Image.new("RGB", (width, height), color=(244, 248, 255))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("arial.ttf", 30)
    except OSError:
        font = ImageFont.load_default()

    for _ in range(8):
        x1 = secrets.randbelow(width)
        y1 = secrets.randbelow(height)
        x2 = secrets.randbelow(width)
        y2 = secrets.randbelow(height)
        line_color = (
            80 + secrets.randbelow(120),
            90 + secrets.randbelow(110),
            100 + secrets.randbelow(100),
        )
        draw.line((x1, y1, x2, y2), fill=line_color, width=1)

    for _ in range(220):
        px = secrets.randbelow(width)
        py = secrets.randbelow(height)
        point_color = (
            110 + secrets.randbelow(130),
            120 + secrets.randbelow(120),
            130 + secrets.randbelow(110),
        )
        draw.point((px, py), fill=point_color)

    slot_width = width / (len(answer) + 1)
    for index, char in enumerate(answer):
        char_layer = Image.new("RGBA", (56, 56), (0, 0, 0, 0))
        char_draw = ImageDraw.Draw(char_layer)
        char_color = (
            15 + secrets.randbelow(40),
            20 + secrets.randbelow(50),
            30 + secrets.randbelow(60),
            255,
        )
        char_draw.text((28, 28), char, font=font, fill=char_color, anchor="mm")

        rotate_angle = secrets.randbelow(41) - 20
        rotated = char_layer.rotate(rotate_angle, expand=True)

        center_x = int(slot_width * (index + 1))
        center_y = (height // 2) + (secrets.randbelow(17) - 8)
        paste_x = center_x - (rotated.width // 2)
        paste_y = center_y - (rotated.height // 2)
        image.paste(rotated, (paste_x, paste_y), rotated)

    for _ in range(4):
        left = secrets.randbelow(width // 2)
        top = secrets.randbelow(height // 2)
        right = left + (width // 2) + secrets.randbelow(width // 3)
        bottom = top + (height // 2) + secrets.randbelow(height // 3)
        start = secrets.randbelow(180)
        end = start + 120 + secrets.randbelow(120)
        arc_color = (
            60 + secrets.randbelow(80),
            80 + secrets.randbelow(90),
            100 + secrets.randbelow(100),
        )
        draw.arc(
            (left, top, right, bottom), start=start, end=end, fill=arc_color, width=1
        )

    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def generate_captcha_challenge(length: int) -> CaptchaChallenge:
    answer = _build_answer(length)
    image_bytes = _render_captcha_png(answer)
    image_base64 = base64.b64encode(image_bytes).decode("ascii")
    captcha_id = secrets.token_urlsafe(16)
    return CaptchaChallenge(
        captcha_id=captcha_id,
        answer=answer,
        image_base64=image_base64,
    )
