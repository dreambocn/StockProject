from datetime import UTC, date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AnalysisEventLink(Base):
    __tablename__ = "analysis_event_links"

    event_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("news_events.id"), primary_key=True
    )
    ts_code: Mapped[str] = mapped_column(String(12), primary_key=True, index=True)
    anchor_trade_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    window_return_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    window_volatility: Mapped[float | None] = mapped_column(Float, nullable=True)
    abnormal_volume_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    correlation_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[str | None] = mapped_column(String(16), nullable=True)
    link_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
