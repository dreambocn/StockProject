"""create market themes domain

Revision ID: 20260331_0004
Revises: 20260331_0003
Create Date: 2026-03-31 16:40:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260331_0004"
down_revision = "20260331_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "market_themes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("theme_code", sa.String(length=64), nullable=False),
        sa.Column("theme_name", sa.String(length=128), nullable=False),
        sa.Column("theme_type", sa.String(length=32), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=64), nullable=True),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_market_themes_theme_code"), "market_themes", ["theme_code"], unique=True)
    op.create_index(op.f("ix_market_themes_theme_name"), "market_themes", ["theme_name"], unique=False)
    op.create_index(op.f("ix_market_themes_theme_type"), "market_themes", ["theme_type"], unique=False)

    op.create_table(
        "market_theme_sync_batches",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("item_count", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_market_theme_sync_batches_status"), "market_theme_sync_batches", ["status"], unique=False)
    op.create_index(op.f("ix_market_theme_sync_batches_source"), "market_theme_sync_batches", ["source"], unique=False)

    op.create_table(
        "market_theme_memberships",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("theme_id", sa.String(length=36), nullable=False),
        sa.Column("ts_code", sa.String(length=12), nullable=False),
        sa.Column("match_score", sa.Integer(), nullable=False),
        sa.Column("evidence_summary", sa.Text(), nullable=True),
        sa.Column("evidence_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["theme_id"], ["market_themes.id"]),
        sa.ForeignKeyConstraint(["ts_code"], ["stock_instruments.ts_code"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("theme_id", "ts_code", name="uq_market_theme_membership"),
    )
    op.create_index(op.f("ix_market_theme_memberships_theme_id"), "market_theme_memberships", ["theme_id"], unique=False)
    op.create_index(op.f("ix_market_theme_memberships_ts_code"), "market_theme_memberships", ["ts_code"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_market_theme_memberships_ts_code"), table_name="market_theme_memberships")
    op.drop_index(op.f("ix_market_theme_memberships_theme_id"), table_name="market_theme_memberships")
    op.drop_table("market_theme_memberships")

    op.drop_index(op.f("ix_market_theme_sync_batches_source"), table_name="market_theme_sync_batches")
    op.drop_index(op.f("ix_market_theme_sync_batches_status"), table_name="market_theme_sync_batches")
    op.drop_table("market_theme_sync_batches")

    op.drop_index(op.f("ix_market_themes_theme_type"), table_name="market_themes")
    op.drop_index(op.f("ix_market_themes_theme_name"), table_name="market_themes")
    op.drop_index(op.f("ix_market_themes_theme_code"), table_name="market_themes")
    op.drop_table("market_themes")
