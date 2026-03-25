from datetime import UTC, datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class StockSyncCursor(Base):
    __tablename__ = "stock_sync_cursors"

    # cursor_key 按业务维度区分同步进度，避免不同任务相互覆盖。
    cursor_key: Mapped[str] = mapped_column(String(32), primary_key=True)
    cursor_value: Mapped[str] = mapped_column(String(64))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
