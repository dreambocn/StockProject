"""add analysis report evidence snapshot fields

Revision ID: 20260401_0007
Revises: 20260401_0006
Create Date: 2026-04-01 21:05:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260401_0007"
down_revision = "20260401_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "analysis_reports",
        sa.Column("evidence_event_count", sa.Integer(), nullable=True),
    )
    op.add_column(
        "analysis_reports",
        sa.Column("evidence_events", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("analysis_reports", "evidence_events")
    op.drop_column("analysis_reports", "evidence_event_count")
