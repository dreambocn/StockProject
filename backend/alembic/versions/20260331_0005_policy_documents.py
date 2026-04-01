"""create policy documents domain

Revision ID: 20260331_0005
Revises: 20260331_0004
Create Date: 2026-03-31 18:30:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260331_0005"
down_revision = "20260331_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "policy_documents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("source_document_id", sa.String(length=255), nullable=True),
        sa.Column("url_hash", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("document_no", sa.String(length=128), nullable=True),
        sa.Column("issuing_authority", sa.String(length=255), nullable=True),
        sa.Column("policy_level", sa.String(length=64), nullable=True),
        sa.Column("category", sa.String(length=64), nullable=True),
        sa.Column("macro_topic", sa.String(length=64), nullable=True),
        sa.Column("industry_tags_json", sa.JSON(), nullable=True),
        sa.Column("market_tags_json", sa.JSON(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("url", sa.String(length=1024), nullable=False),
        sa.Column("content_text", sa.Text(), nullable=True),
        sa.Column("content_html", sa.Text(), nullable=True),
        sa.Column("raw_payload_json", sa.JSON(), nullable=True),
        sa.Column("metadata_status", sa.String(length=32), nullable=False),
        sa.Column("projection_status", sa.String(length=32), nullable=False),
        sa.Column("sync_job_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source",
            "source_document_id",
            name="uq_policy_documents_source_source_document_id",
        ),
        sa.UniqueConstraint(
            "source",
            "url_hash",
            name="uq_policy_documents_source_url_hash",
        ),
    )
    op.create_index(op.f("ix_policy_documents_source"), "policy_documents", ["source"], unique=False)
    op.create_index(op.f("ix_policy_documents_macro_topic"), "policy_documents", ["macro_topic"], unique=False)
    op.create_index(op.f("ix_policy_documents_published_at"), "policy_documents", ["published_at"], unique=False)
    op.create_index(op.f("ix_policy_documents_sync_job_id"), "policy_documents", ["sync_job_id"], unique=False)

    op.create_table(
        "policy_document_attachments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("attachment_url", sa.String(length=1024), nullable=False),
        sa.Column("attachment_name", sa.String(length=255), nullable=True),
        sa.Column("attachment_type", sa.String(length=64), nullable=True),
        sa.Column("attachment_hash", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["policy_documents.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_policy_document_attachments_attachment_hash"),
        "policy_document_attachments",
        ["attachment_hash"],
        unique=False,
    )
    op.create_index(
        op.f("ix_policy_document_attachments_document_id"),
        "policy_document_attachments",
        ["document_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_policy_document_attachments_document_id"),
        table_name="policy_document_attachments",
    )
    op.drop_index(
        op.f("ix_policy_document_attachments_attachment_hash"),
        table_name="policy_document_attachments",
    )
    op.drop_table("policy_document_attachments")

    op.drop_index(op.f("ix_policy_documents_sync_job_id"), table_name="policy_documents")
    op.drop_index(op.f("ix_policy_documents_published_at"), table_name="policy_documents")
    op.drop_index(op.f("ix_policy_documents_macro_topic"), table_name="policy_documents")
    op.drop_index(op.f("ix_policy_documents_source"), table_name="policy_documents")
    op.drop_table("policy_documents")
