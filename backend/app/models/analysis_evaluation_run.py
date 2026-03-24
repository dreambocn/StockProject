from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AnalysisEvaluationRun(Base):
    __tablename__ = 'analysis_evaluation_runs'

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    run_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    dataset_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey('analysis_evaluation_datasets.id'),
        nullable=False,
        index=True,
    )
    experiment_group_key: Mapped[str] = mapped_column(
        String(128), nullable=False, index=True
    )
    variant_key: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    variant_label: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_profile_key: Mapped[str] = mapped_column(String(64), nullable=False)
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    event_top1_hit_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    factor_top1_accuracy: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    citation_metadata_completeness_rate: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0
    )
    avg_latency_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )
