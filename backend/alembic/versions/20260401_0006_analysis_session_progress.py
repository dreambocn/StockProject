"""add analysis session progress fields

Revision ID: 20260401_0006
Revises: 20260331_0005
Create Date: 2026-04-01 12:10:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260401_0006"
down_revision = "20260331_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "analysis_generation_sessions",
        sa.Column("current_stage", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "analysis_generation_sessions",
        sa.Column("stage_message", sa.Text(), nullable=True),
    )
    op.add_column(
        "analysis_generation_sessions",
        sa.Column("progress_current", sa.Integer(), nullable=True),
    )
    op.add_column(
        "analysis_generation_sessions",
        sa.Column("progress_total", sa.Integer(), nullable=True),
    )
    op.add_column(
        "analysis_generation_sessions",
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("analysis_generation_sessions", "heartbeat_at")
    op.drop_column("analysis_generation_sessions", "progress_total")
    op.drop_column("analysis_generation_sessions", "progress_current")
    op.drop_column("analysis_generation_sessions", "stage_message")
    op.drop_column("analysis_generation_sessions", "current_stage")
