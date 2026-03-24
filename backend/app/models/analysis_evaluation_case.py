from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AnalysisEvaluationCase(Base):
    __tablename__ = 'analysis_evaluation_cases'

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    dataset_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey('analysis_evaluation_datasets.id'),
        nullable=False,
        index=True,
    )
    case_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    ts_code: Mapped[str] = mapped_column(String(12), nullable=False, index=True)
    topic: Mapped[str | None] = mapped_column(String(64), nullable=True)
    anchor_event_title: Mapped[str] = mapped_column(String(255), nullable=False)
    expected_top_factor_key: Mapped[str] = mapped_column(String(64), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
