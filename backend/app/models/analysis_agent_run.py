from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AnalysisAgentRun(Base):
    __tablename__ = "analysis_agent_runs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("analysis_generation_sessions.id"),
        index=True,
        nullable=False,
    )
    report_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("analysis_reports.id"),
        index=True,
        nullable=True,
    )
    role_key: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    role_label: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_snapshot: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    output_payload: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    used_web_search: Mapped[bool] = mapped_column(default=False)
    web_search_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="disabled"
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
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
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
