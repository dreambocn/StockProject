from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import DateTime, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class NewsEvent(Base):
    __tablename__ = "news_events"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    scope: Mapped[str] = mapped_column(String(16), index=True)
    cache_variant: Mapped[str] = mapped_column(
        String(32), index=True, default="default"
    )
    ts_code: Mapped[str | None] = mapped_column(String(12), index=True, nullable=True)
    symbol: Mapped[str | None] = mapped_column(String(16), nullable=True)
    title: Mapped[str] = mapped_column(String(255))
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    publisher: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source: Mapped[str] = mapped_column(String(64))
    macro_topic: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    event_type: Mapped[str | None] = mapped_column(
        String(32), nullable=True, index=True
    )
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
    sentiment_label: Mapped[str | None] = mapped_column(String(16), nullable=True)
    sentiment_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    event_tags: Mapped[str | None] = mapped_column(Text, nullable=True)
    analysis_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", index=True
    )
