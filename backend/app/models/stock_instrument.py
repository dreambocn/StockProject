from datetime import UTC, date, datetime

from sqlalchemy import Date, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class StockInstrument(Base):
    __tablename__ = "stock_instruments"

    # 基础证券信息来自外部数据源，作为其他行情与事件的主表引用。
    ts_code: Mapped[str] = mapped_column(String(12), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(10), index=True)
    name: Mapped[str] = mapped_column(String(64), index=True)
    area: Mapped[str | None] = mapped_column(String(32), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(64), nullable=True)
    fullname: Mapped[str | None] = mapped_column(String(128), nullable=True)
    enname: Mapped[str | None] = mapped_column(String(256), nullable=True)
    cnspell: Mapped[str | None] = mapped_column(String(32), nullable=True)
    market: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    exchange: Mapped[str | None] = mapped_column(String(8), nullable=True, index=True)
    curr_type: Mapped[str | None] = mapped_column(String(8), nullable=True)
    # list_status 参考 tushare 口径，常见值 L(上市)/D(退市)/P(暂停)。
    list_status: Mapped[str] = mapped_column(String(1), default="L", index=True)
    list_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    delist_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_hs: Mapped[str | None] = mapped_column(String(1), nullable=True, index=True)
    act_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    act_ent_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
