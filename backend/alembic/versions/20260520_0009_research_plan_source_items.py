"""add research plan and source items

Revision ID: 20260520_0009
Revises: 20260412_0008
Create Date: 2026-05-20 23:05:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260520_0009"
down_revision = "20260412_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "analysis_generation_sessions",
        sa.Column("research_plan", sa.JSON(), nullable=True),
    )
    op.add_column(
        "analysis_reports",
        sa.Column("research_plan", sa.JSON(), nullable=True),
    )
    op.add_column(
        "analysis_reports",
        sa.Column("source_items", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("analysis_reports", "source_items")
    op.drop_column("analysis_reports", "research_plan")
    op.drop_column("analysis_generation_sessions", "research_plan")
