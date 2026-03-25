import secrets
import string


# 场景常量用于区分不同验证码用途，避免互相串用。
REGISTER_EMAIL_SCENE = "register"
CHANGE_PASSWORD_EMAIL_SCENE = "change_password"
RESET_PASSWORD_EMAIL_SCENE = "reset_password"


def generate_email_verification_code(length: int) -> str:
    # 验证码统一为纯数字，降低用户输入成本，并与前端交互保持一致。
    digits = string.digits
    # 使用 secrets 生成安全随机验证码，避免可预测序列被利用。
    return "".join(secrets.choice(digits) for _ in range(length))
