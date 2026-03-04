from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class StockAdjFactor(Base):
    __tablename__ = "stock_adj_factors"

    ts_code: Mapped[str] = mapped_column(
        String(12), ForeignKey("stock_instruments.ts_code"), primary_key=True
    )
    trade_date: Mapped[date] = mapped_column(Date, primary_key=True)
    adj_factor: Mapped[Decimal] = mapped_column(Numeric(20, 10))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
