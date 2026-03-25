from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class WebSourceMetadataCache(Base):
    __tablename__ = "web_source_metadata_cache"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    # url_hash 用于快速去重与缓存命中，避免存储超长索引。
    url_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    resolved_title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    resolved_source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    resolved_domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    resolved_published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    metadata_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="unavailable", index=True
    )
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    # expires_at 控制缓存失效时间，避免重复抓取相同页面。
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
