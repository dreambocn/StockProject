from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PolicyDocumentAttachment(Base):
    __tablename__ = "policy_document_attachments"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    document_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("policy_documents.id"),
        nullable=False,
        index=True,
    )
    attachment_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    attachment_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    attachment_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    attachment_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        index=True,
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
