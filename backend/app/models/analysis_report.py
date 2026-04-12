from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Integer, JSON, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AnalysisReport(Base):
    __tablename__ = "analysis_reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    ts_code: Mapped[str] = mapped_column(String(12), index=True)
    # status 标识报告生命周期，供前端显示生成进度。
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    risk_points: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    factor_breakdown: Mapped[list[dict[str, object]] | None] = mapped_column(JSON, nullable=True)
    topic: Mapped[str | None] = mapped_column(String(64), nullable=True)
    published_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    trigger_source: Mapped[str] = mapped_column(
        String(32), nullable=False, default="manual", index=True
    )
    # used_web_search 表示本次是否实际调用了外部检索能力。
    used_web_search: Mapped[bool] = mapped_column(Boolean, default=False)
    web_search_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="disabled"
    )
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    content_format: Mapped[str] = mapped_column(
        String(16), nullable=False, default="markdown"
    )
    analysis_mode: Mapped[str] = mapped_column(
        String(32), nullable=False, default="single", index=True
    )
    orchestrator_version: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    selected_hypothesis: Mapped[str | None] = mapped_column(String(64), nullable=True)
    decision_confidence: Mapped[str | None] = mapped_column(String(16), nullable=True)
    decision_reason_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    # anchor_event_* 用于把报告锚定到关键事件，便于跨页面跳转。
    anchor_event_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True
    )
    anchor_event_title: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    structured_sources: Mapped[list[dict[str, object]] | None] = mapped_column(
        JSON, nullable=True
    )
    evidence_event_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    evidence_events: Mapped[list[dict[str, object]] | None] = mapped_column(
        JSON, nullable=True
    )
    web_sources: Mapped[list[dict[str, object]] | None] = mapped_column(
        JSON, nullable=True
    )
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
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
