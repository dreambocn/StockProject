from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, JSON, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MarketThemeMembership(Base):
    __tablename__ = "market_theme_memberships"
    __table_args__ = (
        UniqueConstraint("theme_id", "ts_code", name="uq_market_theme_membership"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    theme_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("market_themes.id"),
        nullable=False,
        index=True,
    )
    ts_code: Mapped[str] = mapped_column(
        String(12),
        ForeignKey("stock_instruments.ts_code"),
        nullable=False,
        index=True,
    )
    match_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    evidence_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_json: Mapped[list[dict[str, object]] | list[str] | None] = mapped_column(
        JSON,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
