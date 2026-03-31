from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class NewsFetchBatch(Base):
    __tablename__ = "news_fetch_batches"
    __table_args__ = (
        Index(
            "ix_news_fetch_batches_scope_cache_variant_fetched_at",
            "scope",
            "cache_variant",
            "fetched_at",
        ),
        Index(
            "ix_news_fetch_batches_scope_ts_code_cache_variant_fetched_at",
            "scope",
            "ts_code",
            "cache_variant",
            "fetched_at",
        ),
        Index(
            "ix_news_fetch_batches_status_finished_at",
            "status",
            "finished_at",
        ),
        Index(
            "ix_news_fetch_batches_trigger_source_finished_at",
            "trigger_source",
            "finished_at",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    system_job_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("system_job_runs.id"),
        nullable=True,
        index=True,
    )
    scope: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    cache_variant: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    ts_code: Mapped[str | None] = mapped_column(String(12), nullable=True, index=True)
    trigger_source: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # row_count_* 分别记录原始、映射、落库数量，用于追踪降级与过滤比例。
    row_count_raw: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    row_count_mapped: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    row_count_persisted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    provider_stats_json: Mapped[list[dict[str, object]] | None] = mapped_column(
        JSON, nullable=True
    )
    # degrade_reasons_json 保存降级原因列表，便于排查外部依赖异常。
    degrade_reasons_json: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
