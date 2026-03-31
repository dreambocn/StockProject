from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.system_job_run import SystemJobRun


async def list_job_runs(
    session: AsyncSession,
    *,
    job_type: str | None = None,
    status: str | None = None,
    trigger_source: str | None = None,
    resource_key: str | None = None,
    started_from: datetime | None = None,
    started_to: datetime | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[SystemJobRun], int]:
    statement = select(SystemJobRun)
    if job_type:
        statement = statement.where(SystemJobRun.job_type == job_type.strip())
    if status:
        statement = statement.where(SystemJobRun.status == status.strip().lower())
    if trigger_source:
        statement = statement.where(
            SystemJobRun.trigger_source == trigger_source.strip()
        )
    if resource_key:
        statement = statement.where(
            SystemJobRun.resource_key.ilike(f"%{resource_key.strip()}%")
        )
    if started_from is not None:
        statement = statement.where(SystemJobRun.started_at >= started_from)
    if started_to is not None:
        statement = statement.where(SystemJobRun.started_at <= started_to)

    total = int(
        (
            await session.execute(
                select(func.count()).select_from(statement.subquery())
            )
        ).scalar_one()
    )

    items = (
        await session.execute(
            statement
            .order_by(
                SystemJobRun.created_at.desc(),
                SystemJobRun.id.desc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    return items, total


async def get_job_status_counts(session: AsyncSession) -> dict[str, int]:
    rows = (
        await session.execute(
            select(SystemJobRun.status, func.count())
            .group_by(SystemJobRun.status)
        )
    ).all()
    return {str(status): int(count) for status, count in rows if status}


async def get_job_type_counts(session: AsyncSession) -> dict[str, int]:
    rows = (
        await session.execute(
            select(SystemJobRun.job_type, func.count())
            .group_by(SystemJobRun.job_type)
        )
    ).all()
    return {str(job_type): int(count) for job_type, count in rows if job_type}


async def list_recent_failed_jobs(
    session: AsyncSession,
    *,
    limit: int = 5,
) -> list[SystemJobRun]:
    return (
        await session.execute(
            select(SystemJobRun)
            .where(SystemJobRun.status == "failed")
            .order_by(
                SystemJobRun.finished_at.desc(),
                SystemJobRun.created_at.desc(),
            )
            .limit(limit)
        )
    ).scalars().all()
