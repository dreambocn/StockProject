from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AnalysisEvaluationCaseResult(Base):
    __tablename__ = 'analysis_evaluation_case_results'
    __table_args__ = (
        UniqueConstraint('run_id', 'case_id', name='uq_analysis_evaluation_run_case'),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey('analysis_evaluation_runs.id'),
        nullable=False,
        index=True,
    )
    case_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey('analysis_evaluation_cases.id'),
        nullable=False,
        index=True,
    )
    event_top1_hit: Mapped[bool] = mapped_column(nullable=False, default=False)
    factor_top1_hit: Mapped[bool] = mapped_column(nullable=False, default=False)
    citation_metadata_completeness_rate: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0
    )
    latency_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    top_event_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    top_factor_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    web_source_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    result_snapshot: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
