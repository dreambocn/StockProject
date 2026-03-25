from datetime import datetime, UTC
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


USER_LEVEL_USER = "user"
USER_LEVEL_ADMIN = "admin"


class User(Base):
    __tablename__ = "users"

    # 使用字符串 UUID 作为主键，便于跨系统交互且避免自增 ID 可枚举风险。
    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    # username/email 唯一约束用于登录标识，避免多账号绑定同一凭据。
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    # is_active 用于禁用账号的访问，服务层必须回库校验。
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # user_level 控制管理员权限，路由守卫依赖该字段判断访问边界。
    user_level: Mapped[str] = mapped_column(
        String(16), default=USER_LEVEL_USER, index=True
    )
    # 审计字段：用于追踪账号创建/更新时间及最近登录行为。
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
