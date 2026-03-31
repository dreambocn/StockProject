"""add analysis runtime metadata

Revision ID: 20260331_0003
Revises: 20260331_0002
Create Date: 2026-03-31 16:35:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260331_0003"
down_revision = "20260331_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table_name in ("analysis_generation_sessions", "analysis_reports"):
        op.add_column(
            table_name,
            sa.Column("prompt_version", sa.String(length=32), nullable=True),
        )
        op.add_column(
            table_name,
            sa.Column("model_name", sa.String(length=128), nullable=True),
        )
        op.add_column(
            table_name,
            sa.Column("reasoning_effort", sa.String(length=32), nullable=True),
        )
        op.add_column(
            table_name,
            sa.Column("token_usage_input", sa.Integer(), nullable=True),
        )
        op.add_column(
            table_name,
            sa.Column("token_usage_output", sa.Integer(), nullable=True),
        )
        op.add_column(
            table_name,
            sa.Column("cost_estimate", sa.Numeric(precision=12, scale=6), nullable=True),
        )
        op.add_column(
            table_name,
            sa.Column("failure_type", sa.String(length=64), nullable=True),
        )


def downgrade() -> None:
    for table_name in ("analysis_reports", "analysis_generation_sessions"):
        op.drop_column(table_name, "failure_type")
        op.drop_column(table_name, "cost_estimate")
        op.drop_column(table_name, "token_usage_output")
        op.drop_column(table_name, "token_usage_input")
        op.drop_column(table_name, "reasoning_effort")
        op.drop_column(table_name, "model_name")
        op.drop_column(table_name, "prompt_version")
