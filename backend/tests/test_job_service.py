import asyncio
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models.system_job_run import SystemJobRun
from app.services.job_service import (
    JOB_STATUS_PARTIAL,
    JOB_STATUS_QUEUED,
    create_job_run,
    finish_job_run,
    mark_job_running,
    touch_job_heartbeat,
)


def test_job_service_lifecycle(tmp_path) -> None:
    db_file = tmp_path / "job-service.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_file.as_posix()}")
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    async def run_test() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        async with session_maker() as session:
            job = await create_job_run(
                session,
                job_type="analysis_generate",
                status=JOB_STATUS_QUEUED,
                trigger_source="manual",
                resource_type="stock",
                resource_key="600519.SH",
                summary="已入队",
            )
            assert job.status == JOB_STATUS_QUEUED

            await mark_job_running(session, job=job, summary="执行中")
            assert job.status == "running"
            assert job.started_at is not None

            await touch_job_heartbeat(
                session,
                job=job,
                heartbeat_at=datetime(2026, 3, 31, 10, 0, tzinfo=UTC),
            )
            assert job.heartbeat_at is not None

            await finish_job_run(
                session,
                job=job,
                status=JOB_STATUS_PARTIAL,
                summary="已降级完成",
                metrics_json={"event_count": 0},
            )
            await session.commit()

        async with session_maker() as session:
            stored = (
                await session.execute(select(SystemJobRun).limit(1))
            ).scalar_one()
            assert stored.status == JOB_STATUS_PARTIAL
            assert stored.summary == "已降级完成"
            assert stored.duration_ms is not None
            assert stored.metrics_json == {"event_count": 0}

        await engine.dispose()

    asyncio.run(run_test())
