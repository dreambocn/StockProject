from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AnalysisGenerationSession(Base):
    __tablename__ = "analysis_generation_sessions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    analysis_key: Mapped[str] = mapped_column(String(256), index=True)
    ts_code: Mapped[str] = mapped_column(String(12), index=True)
    topic: Mapped[str | None] = mapped_column(String(64), nullable=True)
    anchor_event_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True
    )
    use_web_search: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    # trigger_source_group 用于区分批量任务来源，便于队列聚合与统计。
    trigger_source: Mapped[str] = mapped_column(
        String(32), nullable=False, default="manual", index=True
    )
    trigger_source_group: Mapped[str] = mapped_column(
        String(32), nullable=False, default="manual", index=True
    )
    # status 代表会话执行状态，避免重复生成。
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="queued", index=True
    )
    system_job_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("system_job_runs.id"),
        nullable=True,
        index=True,
    )
    report_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("analysis_reports.id"), nullable=True
    )
    summary_preview: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    reasoning_effort: Mapped[str | None] = mapped_column(String(32), nullable=True)
    token_usage_input: Mapped[int | None] = mapped_column(nullable=True)
    token_usage_output: Mapped[int | None] = mapped_column(nullable=True)
    cost_estimate: Mapped[float | None] = mapped_column(
        Numeric(precision=12, scale=6),
        nullable=True,
    )
    failure_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
