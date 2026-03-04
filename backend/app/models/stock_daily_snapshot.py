from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class StockDailySnapshot(Base):
    __tablename__ = "stock_daily_snapshots"

    ts_code: Mapped[str] = mapped_column(
        String(12), ForeignKey("stock_instruments.ts_code"), primary_key=True
    )
    trade_date: Mapped[date] = mapped_column(Date, primary_key=True)
    open: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    high: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    low: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    close: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    pre_close: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    change: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    pct_chg: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    vol: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    turnover_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    volume_ratio: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    pe: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    pb: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    total_mv: Mapped[Decimal | None] = mapped_column(Numeric(24, 4), nullable=True)
    circ_mv: Mapped[Decimal | None] = mapped_column(Numeric(24, 4), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
