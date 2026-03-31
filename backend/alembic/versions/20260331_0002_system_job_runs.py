"""create system job runs

Revision ID: 20260331_0002
Revises: 20260331_0001
Create Date: 2026-03-31 16:10:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260331_0002"
down_revision = "20260331_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    should_create_fk = bind.dialect.name != "sqlite"

    op.create_table(
        "system_job_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("job_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("trigger_source", sa.String(length=64), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=True),
        sa.Column("resource_key", sa.String(length=255), nullable=True),
        sa.Column("idempotency_key", sa.String(length=255), nullable=True),
        sa.Column("linked_entity_type", sa.String(length=64), nullable=True),
        sa.Column("linked_entity_id", sa.String(length=36), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=True),
        sa.Column("metrics_json", sa.JSON(), nullable=True),
        sa.Column("error_type", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_system_job_runs_job_type"), "system_job_runs", ["job_type"], unique=False)
    op.create_index(op.f("ix_system_job_runs_status"), "system_job_runs", ["status"], unique=False)
    op.create_index(op.f("ix_system_job_runs_trigger_source"), "system_job_runs", ["trigger_source"], unique=False)
    op.create_index(op.f("ix_system_job_runs_resource_type"), "system_job_runs", ["resource_type"], unique=False)
    op.create_index(op.f("ix_system_job_runs_resource_key"), "system_job_runs", ["resource_key"], unique=False)
    op.create_index(op.f("ix_system_job_runs_idempotency_key"), "system_job_runs", ["idempotency_key"], unique=False)
    op.create_index(op.f("ix_system_job_runs_started_at"), "system_job_runs", ["started_at"], unique=False)
    op.create_index(op.f("ix_system_job_runs_heartbeat_at"), "system_job_runs", ["heartbeat_at"], unique=False)
    op.create_index(op.f("ix_system_job_runs_finished_at"), "system_job_runs", ["finished_at"], unique=False)
    op.create_index(
        "ix_system_job_runs_job_type_status_started_at",
        "system_job_runs",
        ["job_type", "status", "started_at"],
        unique=False,
    )
    op.create_index(
        "ix_system_job_runs_trigger_source_started_at",
        "system_job_runs",
        ["trigger_source", "started_at"],
        unique=False,
    )
    op.create_index(
        "ix_system_job_runs_resource_type_resource_key",
        "system_job_runs",
        ["resource_type", "resource_key"],
        unique=False,
    )

    op.add_column(
        "analysis_generation_sessions",
        sa.Column("system_job_id", sa.String(length=36), nullable=True),
    )
    op.create_index(
        op.f("ix_analysis_generation_sessions_system_job_id"),
        "analysis_generation_sessions",
        ["system_job_id"],
        unique=False,
    )
    if should_create_fk:
        op.create_foreign_key(
            "fk_analysis_generation_sessions_system_job_id",
            "analysis_generation_sessions",
            "system_job_runs",
            ["system_job_id"],
            ["id"],
        )

    op.add_column(
        "news_fetch_batches",
        sa.Column("system_job_id", sa.String(length=36), nullable=True),
    )
    op.create_index(
        op.f("ix_news_fetch_batches_system_job_id"),
        "news_fetch_batches",
        ["system_job_id"],
        unique=False,
    )
    if should_create_fk:
        op.create_foreign_key(
            "fk_news_fetch_batches_system_job_id",
            "news_fetch_batches",
            "system_job_runs",
            ["system_job_id"],
            ["id"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    should_drop_fk = bind.dialect.name != "sqlite"

    if should_drop_fk:
        op.drop_constraint(
            "fk_news_fetch_batches_system_job_id",
            "news_fetch_batches",
            type_="foreignkey",
        )
    op.drop_index(op.f("ix_news_fetch_batches_system_job_id"), table_name="news_fetch_batches")
    op.drop_column("news_fetch_batches", "system_job_id")

    if should_drop_fk:
        op.drop_constraint(
            "fk_analysis_generation_sessions_system_job_id",
            "analysis_generation_sessions",
            type_="foreignkey",
        )
    op.drop_index(
        op.f("ix_analysis_generation_sessions_system_job_id"),
        table_name="analysis_generation_sessions",
    )
    op.drop_column("analysis_generation_sessions", "system_job_id")

    op.drop_index("ix_system_job_runs_resource_type_resource_key", table_name="system_job_runs")
    op.drop_index("ix_system_job_runs_trigger_source_started_at", table_name="system_job_runs")
    op.drop_index("ix_system_job_runs_job_type_status_started_at", table_name="system_job_runs")
    op.drop_index(op.f("ix_system_job_runs_finished_at"), table_name="system_job_runs")
    op.drop_index(op.f("ix_system_job_runs_heartbeat_at"), table_name="system_job_runs")
    op.drop_index(op.f("ix_system_job_runs_started_at"), table_name="system_job_runs")
    op.drop_index(op.f("ix_system_job_runs_idempotency_key"), table_name="system_job_runs")
    op.drop_index(op.f("ix_system_job_runs_resource_key"), table_name="system_job_runs")
    op.drop_index(op.f("ix_system_job_runs_resource_type"), table_name="system_job_runs")
    op.drop_index(op.f("ix_system_job_runs_trigger_source"), table_name="system_job_runs")
    op.drop_index(op.f("ix_system_job_runs_status"), table_name="system_job_runs")
    op.drop_index(op.f("ix_system_job_runs_job_type"), table_name="system_job_runs")
    op.drop_table("system_job_runs")
