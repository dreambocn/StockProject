from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.system_job_run import SystemJobRun


JOB_STATUS_QUEUED = "queued"
JOB_STATUS_RUNNING = "running"
JOB_STATUS_SUCCESS = "success"
JOB_STATUS_PARTIAL = "partial"
JOB_STATUS_FAILED = "failed"
JOB_STATUSES = {
    JOB_STATUS_QUEUED,
    JOB_STATUS_RUNNING,
    JOB_STATUS_SUCCESS,
    JOB_STATUS_PARTIAL,
    JOB_STATUS_FAILED,
}


def _normalize_datetime(value: datetime | None) -> datetime:
    resolved = value or datetime.now(UTC)
    if resolved.tzinfo is None:
        return resolved.replace(tzinfo=UTC)
    return resolved.astimezone(UTC)


def _normalize_status(status: str) -> str:
    normalized = status.strip().lower()
    if normalized not in JOB_STATUSES:
        raise ValueError("invalid job status")
    return normalized


def _trim_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _to_duration_ms(
    *,
    started_at: datetime | None,
    finished_at: datetime | None,
) -> int | None:
    if started_at is None or finished_at is None:
        return None
    normalized_started_at = _normalize_datetime(started_at)
    normalized_finished_at = _normalize_datetime(finished_at)
    duration_ms = int(
        (normalized_finished_at - normalized_started_at).total_seconds() * 1000
    )
    return max(duration_ms, 0)


async def create_job_run(
    session: AsyncSession,
    *,
    job_type: str,
    trigger_source: str,
    resource_type: str | None = None,
    resource_key: str | None = None,
    idempotency_key: str | None = None,
    linked_entity_type: str | None = None,
    linked_entity_id: str | None = None,
    summary: str | None = None,
    payload_json: dict[str, object] | list[object] | None = None,
    metrics_json: dict[str, object] | list[object] | None = None,
    status: str = JOB_STATUS_QUEUED,
    started_at: datetime | None = None,
    heartbeat_at: datetime | None = None,
) -> SystemJobRun:
    normalized_status = _normalize_status(status)
    resolved_started_at = (
        _normalize_datetime(started_at)
        if normalized_status == JOB_STATUS_RUNNING
        else (None if started_at is None else _normalize_datetime(started_at))
    )
    resolved_heartbeat_at = (
        _normalize_datetime(heartbeat_at)
        if heartbeat_at is not None
        else (resolved_started_at if normalized_status == JOB_STATUS_RUNNING else None)
    )
    row = SystemJobRun(
        job_type=job_type.strip(),
        status=normalized_status,
        trigger_source=trigger_source.strip() or "unknown",
        resource_type=_trim_text(resource_type),
        resource_key=_trim_text(resource_key),
        idempotency_key=_trim_text(idempotency_key),
        linked_entity_type=_trim_text(linked_entity_type),
        linked_entity_id=_trim_text(linked_entity_id),
        summary=_trim_text(summary),
        payload_json=payload_json,
        metrics_json=metrics_json,
        started_at=resolved_started_at,
        heartbeat_at=resolved_heartbeat_at,
    )
    session.add(row)
    await session.flush()
    return row


async def mark_job_running(
    session: AsyncSession,
    *,
    job: SystemJobRun,
    summary: str | None = None,
    payload_json: dict[str, object] | list[object] | None = None,
    metrics_json: dict[str, object] | list[object] | None = None,
    linked_entity_type: str | None = None,
    linked_entity_id: str | None = None,
    heartbeat_at: datetime | None = None,
) -> SystemJobRun:
    resolved_now = _normalize_datetime(heartbeat_at)
    job.status = JOB_STATUS_RUNNING
    job.started_at = job.started_at or resolved_now
    job.heartbeat_at = resolved_now
    if summary is not None:
        job.summary = _trim_text(summary)
    if payload_json is not None:
        job.payload_json = payload_json
    if metrics_json is not None:
        job.metrics_json = metrics_json
    if linked_entity_type is not None:
        job.linked_entity_type = _trim_text(linked_entity_type)
    if linked_entity_id is not None:
        job.linked_entity_id = _trim_text(linked_entity_id)
    await session.flush()
    return job


async def touch_job_heartbeat(
    session: AsyncSession,
    *,
    job: SystemJobRun,
    heartbeat_at: datetime | None = None,
    metrics_json: dict[str, object] | list[object] | None = None,
    summary: str | None = None,
) -> SystemJobRun:
    job.heartbeat_at = _normalize_datetime(heartbeat_at)
    if metrics_json is not None:
        job.metrics_json = metrics_json
    if summary is not None:
        job.summary = _trim_text(summary)
    await session.flush()
    return job


async def finish_job_run(
    session: AsyncSession,
    *,
    job: SystemJobRun,
    status: str,
    summary: str | None = None,
    payload_json: dict[str, object] | list[object] | None = None,
    metrics_json: dict[str, object] | list[object] | None = None,
    error_type: str | None = None,
    error_message: str | None = None,
    linked_entity_type: str | None = None,
    linked_entity_id: str | None = None,
    finished_at: datetime | None = None,
) -> SystemJobRun:
    normalized_status = _normalize_status(status)
    if normalized_status not in {
        JOB_STATUS_SUCCESS,
        JOB_STATUS_PARTIAL,
        JOB_STATUS_FAILED,
    }:
        raise ValueError("final job status must be success, partial, or failed")

    resolved_finished_at = _normalize_datetime(finished_at)
    job.status = normalized_status
    job.finished_at = resolved_finished_at
    job.heartbeat_at = resolved_finished_at
    job.duration_ms = _to_duration_ms(
        started_at=job.started_at,
        finished_at=resolved_finished_at,
    )
    if summary is not None:
        job.summary = _trim_text(summary)
    if payload_json is not None:
        job.payload_json = payload_json
    if metrics_json is not None:
        job.metrics_json = metrics_json
    job.error_type = _trim_text(error_type)
    job.error_message = _trim_text(error_message)
    if linked_entity_type is not None:
        job.linked_entity_type = _trim_text(linked_entity_type)
    if linked_entity_id is not None:
        job.linked_entity_id = _trim_text(linked_entity_id)
    await session.flush()
    return job
