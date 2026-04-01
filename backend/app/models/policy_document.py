from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import DateTime, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PolicyDocument(Base):
    __tablename__ = "policy_documents"
    __table_args__ = (
        UniqueConstraint(
            "source",
            "source_document_id",
            name="uq_policy_documents_source_source_document_id",
        ),
        UniqueConstraint(
            "source",
            "url_hash",
            name="uq_policy_documents_source_url_hash",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    source: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_document_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    url_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    document_no: Mapped[str | None] = mapped_column(String(128), nullable=True)
    issuing_authority: Mapped[str | None] = mapped_column(String(255), nullable=True)
    policy_level: Mapped[str | None] = mapped_column(String(64), nullable=True)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    macro_topic: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    industry_tags_json: Mapped[list[object] | dict[str, object] | None] = mapped_column(
        JSON,
        nullable=True,
    )
    market_tags_json: Mapped[list[object] | dict[str, object] | None] = mapped_column(
        JSON,
        nullable=True,
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    effective_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    expired_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    content_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_payload_json: Mapped[dict[str, object] | list[object] | None] = mapped_column(
        JSON,
        nullable=True,
    )
    metadata_status: Mapped[str] = mapped_column(String(32), nullable=False)
    projection_status: Mapped[str] = mapped_column(String(32), nullable=False)
    sync_job_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
