from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.schemas.auth import PASSWORD_POLICY_MESSAGE


UserLevel = Literal["user", "admin"]


def _is_strong_password(value: str) -> bool:
    has_upper = any(ch.isupper() for ch in value)
    has_lower = any(ch.islower() for ch in value)
    has_digit = any(ch.isdigit() for ch in value)
    has_symbol = any(not ch.isalnum() for ch in value)
    return has_upper and has_lower and has_digit and has_symbol


class AdminCreateUserRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    user_level: UserLevel = "user"

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, value: str) -> str:
        # 管理员创建账号同样执行强密码策略，避免后门式弱口令账号进入系统。
        if not _is_strong_password(value):
            raise ValueError(PASSWORD_POLICY_MESSAGE)

        return value


class AdminUserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    username: str
    email: EmailStr
    is_active: bool
    user_level: UserLevel
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None
