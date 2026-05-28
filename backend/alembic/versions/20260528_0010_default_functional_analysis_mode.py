"""default analysis mode to functional multi agent

Revision ID: 20260528_0010
Revises: 20260520_0009
Create Date: 2026-05-28 23:10:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260528_0010"
down_revision = "20260520_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("analysis_generation_sessions") as batch_op:
        batch_op.alter_column(
            "analysis_mode",
            server_default="functional_multi_agent",
            existing_type=sa.String(length=32),
        )
    with op.batch_alter_table("analysis_reports") as batch_op:
        batch_op.alter_column(
            "analysis_mode",
            server_default="functional_multi_agent",
            existing_type=sa.String(length=32),
        )


def downgrade() -> None:
    with op.batch_alter_table("analysis_reports") as batch_op:
        batch_op.alter_column(
            "analysis_mode",
            server_default="single",
            existing_type=sa.String(length=32),
        )
    with op.batch_alter_table("analysis_generation_sessions") as batch_op:
        batch_op.alter_column(
            "analysis_mode",
            server_default="single",
            existing_type=sa.String(length=32),
        )
