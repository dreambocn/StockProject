from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UserWatchlistItem(Base):
    __tablename__ = "user_watchlist_items"
    __table_args__ = (UniqueConstraint("user_id", "ts_code", name="uq_user_watchlist"),)

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    ts_code: Mapped[str] = mapped_column(String(12), index=True)
    hourly_sync_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    daily_analysis_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    web_search_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    last_hourly_sync_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_daily_analysis_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
