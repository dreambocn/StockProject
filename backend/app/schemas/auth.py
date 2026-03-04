from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


PASSWORD_POLICY_MESSAGE = "Password must be 8-128 chars and include uppercase, lowercase, number, and special character"


def _is_strong_password(value: str) -> bool:
    # 服务端密码策略兜底：即使前端校验被绕过，后端仍强制执行。
    has_upper = any(ch.isupper() for ch in value)
    has_lower = any(ch.islower() for ch in value)
    has_digit = any(ch.isdigit() for ch in value)
    has_symbol = any(not ch.isalnum() for ch in value)
    return has_upper and has_lower and has_digit and has_symbol


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    email: EmailStr
    email_code: str = Field(min_length=4, max_length=12)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, value: str) -> str:
        # 注册链路强制密码复杂度，降低弱口令风险。
        if not _is_strong_password(value):
            raise ValueError(PASSWORD_POLICY_MESSAGE)

        return value


class LoginRequest(BaseModel):
    account: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    captcha_id: str | None = None
    captcha_code: str | None = None


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=8, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)
    email_code: str = Field(min_length=4, max_length=12)

    @field_validator("new_password")
    @classmethod
    def validate_new_password_strength(cls, value: str) -> str:
        # 改密与注册采用同一策略，避免策略不一致导致安全缺口。
        if not _is_strong_password(value):
            raise ValueError(PASSWORD_POLICY_MESSAGE)

        return value


class TokenPairResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    username: str
    email: EmailStr
    is_active: bool


class MessageResponse(BaseModel):
    message: str


class CaptchaChallengeResponse(BaseModel):
    captcha_id: str
    image_base64: str
    expires_in: int


class RegisterEmailCodeRequest(BaseModel):
    email: EmailStr


class EmailCodeSendResponse(BaseModel):
    message: str
    expires_in: int
    cooldown_in: int


class ResetPasswordEmailCodeRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    email: EmailStr
    email_code: str = Field(min_length=4, max_length=12)
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def validate_new_password_strength(cls, value: str) -> str:
        # 重置密码同样执行强校验，防止通过找回流程降级密码强度。
        if not _is_strong_password(value):
            raise ValueError(PASSWORD_POLICY_MESSAGE)

        return value
