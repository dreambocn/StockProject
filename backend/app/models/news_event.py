from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import DateTime, Float, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class NewsEvent(Base):
    __tablename__ = "news_events"
    __table_args__ = (
        Index(
            "ix_news_events_scope_cache_variant_fetched_at",
            "scope",
            "cache_variant",
            "fetched_at",
        ),
        Index(
            "ix_news_events_scope_ts_code_cache_variant_fetched_at",
            "scope",
            "ts_code",
            "cache_variant",
            "fetched_at",
        ),
        Index(
            "ix_news_events_scope_cluster_key_fetched_at",
            "scope",
            "cluster_key",
            "fetched_at",
        ),
        Index(
            "ix_news_events_batch_id",
            "batch_id",
        ),
        Index(
            "ix_news_events_scope_topic_published_fetched_created",
            "scope",
            "macro_topic",
            "published_at",
            "fetched_at",
            "created_at",
        ),
        Index(
            "ix_news_events_scope_ts_code_published_fetched_created",
            "scope",
            "ts_code",
            "published_at",
            "fetched_at",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    scope: Mapped[str] = mapped_column(String(16), index=True)
    # cache_variant 用于区分不同缓存口径，避免同范围数据互相覆盖。
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
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="internal")
    external_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    # cluster_key 用于跨来源聚类，去重时优先按此字段合并。
    cluster_key: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    batch_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    # source_priority 越高代表来源权重越高，排序与去重时使用。
    source_priority: Mapped[int] = mapped_column(nullable=False, default=0, index=True)
    # evidence_kind 细分证据类型，便于在前端做分类与筛选。
    evidence_kind: Mapped[str] = mapped_column(String(32), nullable=False, default="hot", index=True)
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
    # analysis_status 代表分析流水线状态，避免重复触发下游任务。
    analysis_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", index=True
    )
