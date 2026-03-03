from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


PASSWORD_POLICY_MESSAGE = "Password must be 8-128 chars and include uppercase, lowercase, number, and special character"


def _is_strong_password(value: str) -> bool:
    has_upper = any(ch.isupper() for ch in value)
    has_lower = any(ch.islower() for ch in value)
    has_digit = any(ch.isdigit() for ch in value)
    has_symbol = any(not ch.isalnum() for ch in value)
    return has_upper and has_lower and has_digit and has_symbol


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, value: str) -> str:
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

    @field_validator("new_password")
    @classmethod
    def validate_new_password_strength(cls, value: str) -> str:
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
