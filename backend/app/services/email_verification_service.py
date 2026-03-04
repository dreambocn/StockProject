import secrets
import string


REGISTER_EMAIL_SCENE = "register"
CHANGE_PASSWORD_EMAIL_SCENE = "change_password"
RESET_PASSWORD_EMAIL_SCENE = "reset_password"


def generate_email_verification_code(length: int) -> str:
    digits = string.digits
    return "".join(secrets.choice(digits) for _ in range(length))
