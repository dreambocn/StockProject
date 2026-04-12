"""add functional multi-agent analysis schema

Revision ID: 20260412_0008
Revises: 20260401_0007
Create Date: 2026-04-12 17:55:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260412_0008"
down_revision = "20260401_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "analysis_generation_sessions",
        sa.Column("analysis_mode", sa.String(length=32), nullable=False, server_default="single"),
    )
    op.add_column(
        "analysis_generation_sessions",
        sa.Column("orchestrator_version", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "analysis_generation_sessions",
        sa.Column("role_count", sa.Integer(), nullable=True),
    )
    op.add_column(
        "analysis_generation_sessions",
        sa.Column("role_completed_count", sa.Integer(), nullable=True),
    )
    op.add_column(
        "analysis_generation_sessions",
        sa.Column("active_role_key", sa.String(length=64), nullable=True),
    )
    op.create_index(
        op.f("ix_analysis_generation_sessions_analysis_mode"),
        "analysis_generation_sessions",
        ["analysis_mode"],
        unique=False,
    )

    op.add_column(
        "analysis_reports",
        sa.Column("analysis_mode", sa.String(length=32), nullable=False, server_default="single"),
    )
    op.add_column(
        "analysis_reports",
        sa.Column("orchestrator_version", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "analysis_reports",
        sa.Column("selected_hypothesis", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "analysis_reports",
        sa.Column("decision_confidence", sa.String(length=16), nullable=True),
    )
    op.add_column(
        "analysis_reports",
        sa.Column("decision_reason_summary", sa.Text(), nullable=True),
    )
    op.create_index(
        op.f("ix_analysis_reports_analysis_mode"),
        "analysis_reports",
        ["analysis_mode"],
        unique=False,
    )

    op.create_table(
        "analysis_agent_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("report_id", sa.String(length=36), nullable=True),
        sa.Column("role_key", sa.String(length=64), nullable=False),
        sa.Column("role_label", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("input_snapshot", sa.JSON(), nullable=True),
        sa.Column("output_payload", sa.JSON(), nullable=True),
        sa.Column("used_web_search", sa.Boolean(), nullable=False),
        sa.Column("web_search_status", sa.String(length=16), nullable=False),
        sa.Column("web_sources", sa.JSON(), nullable=True),
        sa.Column("prompt_version", sa.String(length=32), nullable=True),
        sa.Column("model_name", sa.String(length=128), nullable=True),
        sa.Column("reasoning_effort", sa.String(length=32), nullable=True),
        sa.Column("token_usage_input", sa.Integer(), nullable=True),
        sa.Column("token_usage_output", sa.Integer(), nullable=True),
        sa.Column("cost_estimate", sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column("failure_type", sa.String(length=64), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["report_id"], ["analysis_reports.id"]),
        sa.ForeignKeyConstraint(["session_id"], ["analysis_generation_sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_analysis_agent_runs_report_id"),
        "analysis_agent_runs",
        ["report_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_analysis_agent_runs_role_key"),
        "analysis_agent_runs",
        ["role_key"],
        unique=False,
    )
    op.create_index(
        op.f("ix_analysis_agent_runs_session_id"),
        "analysis_agent_runs",
        ["session_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_analysis_agent_runs_session_id"), table_name="analysis_agent_runs")
    op.drop_index(op.f("ix_analysis_agent_runs_role_key"), table_name="analysis_agent_runs")
    op.drop_index(op.f("ix_analysis_agent_runs_report_id"), table_name="analysis_agent_runs")
    op.drop_table("analysis_agent_runs")

    op.drop_index(op.f("ix_analysis_reports_analysis_mode"), table_name="analysis_reports")
    op.drop_column("analysis_reports", "decision_reason_summary")
    op.drop_column("analysis_reports", "decision_confidence")
    op.drop_column("analysis_reports", "selected_hypothesis")
    op.drop_column("analysis_reports", "orchestrator_version")
    op.drop_column("analysis_reports", "analysis_mode")

    op.drop_index(
        op.f("ix_analysis_generation_sessions_analysis_mode"),
        table_name="analysis_generation_sessions",
    )
    op.drop_column("analysis_generation_sessions", "active_role_key")
    op.drop_column("analysis_generation_sessions", "role_completed_count")
    op.drop_column("analysis_generation_sessions", "role_count")
    op.drop_column("analysis_generation_sessions", "orchestrator_version")
    op.drop_column("analysis_generation_sessions", "analysis_mode")
