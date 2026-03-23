from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import DateTime, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AnalysisReport(Base):
    __tablename__ = "analysis_reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    ts_code: Mapped[str] = mapped_column(String(12), index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    risk_points: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    factor_breakdown: Mapped[list[dict[str, object]] | None] = mapped_column(JSON, nullable=True)
    topic: Mapped[str | None] = mapped_column(String(64), nullable=True)
    published_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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
