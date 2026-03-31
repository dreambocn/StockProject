from datetime import UTC, datetime

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.news_fetch_batch import NewsFetchBatch
from app.models.system_job_run import SystemJobRun
from app.services.job_service import (
    JOB_STATUS_RUNNING,
    create_job_run,
    finish_job_run,
)


NEWS_FETCH_SCOPE_HOT = "hot"
NEWS_FETCH_SCOPE_POLICY = "policy"
NEWS_FETCH_SCOPE_STOCK = "stock"
NEWS_FETCH_SCOPES = {
    NEWS_FETCH_SCOPE_HOT,
    NEWS_FETCH_SCOPE_POLICY,
    NEWS_FETCH_SCOPE_STOCK,
}

NEWS_FETCH_STATUS_RUNNING = "running"
NEWS_FETCH_STATUS_SUCCESS = "success"
NEWS_FETCH_STATUS_PARTIAL = "partial"
NEWS_FETCH_STATUS_FAILED = "failed"
NEWS_FETCH_STATUSES = {
    NEWS_FETCH_STATUS_RUNNING,
    NEWS_FETCH_STATUS_SUCCESS,
    NEWS_FETCH_STATUS_PARTIAL,
    NEWS_FETCH_STATUS_FAILED,
}

LATEST_COMPLETED_BATCH_STATUSES: tuple[str, ...] = (
    NEWS_FETCH_STATUS_SUCCESS,
    NEWS_FETCH_STATUS_PARTIAL,
)

LOGGER = get_logger(__name__)


def _normalize_datetime(value: datetime | None) -> datetime:
    resolved = value or datetime.now(UTC)
    if resolved.tzinfo is None:
        return resolved.replace(tzinfo=UTC)
    return resolved.astimezone(UTC)


def _validate_scope(scope: str) -> str:
    normalized_scope = scope.strip().lower()
    if normalized_scope not in NEWS_FETCH_SCOPES:
        raise ValueError("invalid news fetch scope")
    return normalized_scope


def _validate_status(status: str) -> str:
    normalized_status = status.strip().lower()
    if normalized_status not in NEWS_FETCH_STATUSES:
        raise ValueError("invalid news fetch status")
    return normalized_status


def _truncate_error_message(message: str | None, limit: int = 500) -> str | None:
    if message is None:
        return None
    normalized_message = message.strip()
    if not normalized_message:
        return None
    # 错误信息只保留前 N 字符，避免日志和数据库被异常长文本撑爆。
    return normalized_message[:limit]


async def create_news_fetch_batch(
    session: AsyncSession,
    *,
    scope: str,
    cache_variant: str,
    trigger_source: str,
    ts_code: str | None = None,
    fetched_at: datetime | None = None,
    started_at: datetime | None = None,
) -> NewsFetchBatch:
    normalized_scope = _validate_scope(scope)
    normalized_ts_code = ts_code.strip().upper() if ts_code else None
    if normalized_scope == NEWS_FETCH_SCOPE_STOCK and not normalized_ts_code:
        raise ValueError("stock scope requires ts_code")

    job = await create_job_run(
        session,
        job_type="news_fetch",
        status=JOB_STATUS_RUNNING,
        trigger_source=trigger_source.strip() or "unknown",
        resource_type=normalized_scope,
        resource_key=normalized_ts_code or (cache_variant.strip() or "default"),
        summary="新闻抓取任务执行中",
        payload_json={
            "scope": normalized_scope,
            "cache_variant": cache_variant.strip() or "default",
            "ts_code": normalized_ts_code,
        },
    )
    # 关键流程：批次在启动阶段先写入 running 状态，后续统一由 finalize 更新统计和结论。
    row = NewsFetchBatch(
        system_job_id=job.id,
        scope=normalized_scope,
        cache_variant=cache_variant.strip() or "default",
        ts_code=normalized_ts_code,
        trigger_source=trigger_source.strip() or "unknown",
        status=NEWS_FETCH_STATUS_RUNNING,
        started_at=_normalize_datetime(started_at),
        fetched_at=_normalize_datetime(fetched_at),
        row_count_raw=0,
        row_count_mapped=0,
        row_count_persisted=0,
        provider_stats_json=[],
        degrade_reasons_json=[],
    )
    session.add(row)
    await session.flush()
    job.linked_entity_type = "news_fetch_batch"
    job.linked_entity_id = row.id
    LOGGER.info(
        "event=news_fetch_batch_started batch_id=%s scope=%s cache_variant=%s ts_code=%s trigger_source=%s",
        row.id,
        row.scope,
        row.cache_variant,
        row.ts_code or "-",
        row.trigger_source,
    )
    return row


async def finalize_news_fetch_batch(
    session: AsyncSession,
    *,
    batch: NewsFetchBatch,
    status: str,
    finished_at: datetime | None = None,
    row_count_raw: int = 0,
    row_count_mapped: int = 0,
    row_count_persisted: int = 0,
    provider_stats: list[dict[str, object]] | None = None,
    degrade_reasons: list[str] | None = None,
    error_type: str | None = None,
    error_message: str | None = None,
) -> NewsFetchBatch:
    normalized_status = _validate_status(status)
    if normalized_status == NEWS_FETCH_STATUS_RUNNING:
        raise ValueError("final status cannot be running")

    resolved_finished_at = _normalize_datetime(finished_at)
    resolved_started_at = _normalize_datetime(batch.started_at)
    # duration_ms 以 started_at 为基准，异常时间戳回退为 0。
    duration_ms = int((resolved_finished_at - resolved_started_at).total_seconds() * 1000)
    if duration_ms < 0:
        duration_ms = 0

    batch.status = normalized_status
    batch.finished_at = resolved_finished_at
    batch.duration_ms = duration_ms
    batch.row_count_raw = max(0, int(row_count_raw))
    batch.row_count_mapped = max(0, int(row_count_mapped))
    batch.row_count_persisted = max(0, int(row_count_persisted))
    batch.provider_stats_json = provider_stats or []
    batch.degrade_reasons_json = degrade_reasons or []
    batch.error_type = error_type.strip() if error_type else None
    batch.error_message = _truncate_error_message(error_message)
    if batch.system_job_id:
        job = await session.get(SystemJobRun, batch.system_job_id)
        if job is not None:
            await finish_job_run(
                session,
                job=job,
                status=(
                    "success"
                    if normalized_status == NEWS_FETCH_STATUS_SUCCESS
                    else (
                        "partial"
                        if normalized_status == NEWS_FETCH_STATUS_PARTIAL
                        else "failed"
                    )
                ),
                summary=(
                    "新闻抓取任务完成"
                    if normalized_status != NEWS_FETCH_STATUS_FAILED
                    else "新闻抓取任务失败"
                ),
                metrics_json={
                    "row_count_raw": batch.row_count_raw,
                    "row_count_mapped": batch.row_count_mapped,
                    "row_count_persisted": batch.row_count_persisted,
                    "provider_stats": batch.provider_stats_json or [],
                    "degrade_reasons": batch.degrade_reasons_json or [],
                },
                error_type=batch.error_type,
                error_message=batch.error_message,
                linked_entity_type="news_fetch_batch",
                linked_entity_id=batch.id,
                finished_at=resolved_finished_at,
            )
    await session.flush()
    LOGGER.info(
        "event=news_fetch_batch_finished batch_id=%s status=%s duration_ms=%s raw=%s mapped=%s persisted=%s",
        batch.id,
        batch.status,
        batch.duration_ms,
        batch.row_count_raw,
        batch.row_count_mapped,
        batch.row_count_persisted,
    )
    return batch


def build_latest_news_fetch_batch_statement(
    *,
    scope: str,
    cache_variant: str,
    ts_code: str | None = None,
    statuses: tuple[str, ...] = LATEST_COMPLETED_BATCH_STATUSES,
) -> Select[tuple[NewsFetchBatch]]:
    normalized_scope = _validate_scope(scope)
    normalized_statuses = tuple(_validate_status(status) for status in statuses)
    if not normalized_statuses:
        raise ValueError("statuses cannot be empty")

    statement = (
        select(NewsFetchBatch)
        .where(NewsFetchBatch.scope == normalized_scope)
        .where(NewsFetchBatch.cache_variant == (cache_variant.strip() or "default"))
        .where(NewsFetchBatch.status.in_(normalized_statuses))
    )

    if normalized_scope == NEWS_FETCH_SCOPE_STOCK:
        normalized_ts_code = ts_code.strip().upper() if ts_code else ""
        if not normalized_ts_code:
            raise ValueError("stock scope requires ts_code")
        statement = statement.where(NewsFetchBatch.ts_code == normalized_ts_code)
    elif ts_code is not None and ts_code.strip():
        statement = statement.where(NewsFetchBatch.ts_code == ts_code.strip().upper())

    return statement.order_by(
        NewsFetchBatch.fetched_at.desc(),
        NewsFetchBatch.finished_at.desc(),
        NewsFetchBatch.created_at.desc(),
    )


async def load_latest_news_fetch_batch(
    session: AsyncSession,
    *,
    scope: str,
    cache_variant: str,
    ts_code: str | None = None,
    statuses: tuple[str, ...] = LATEST_COMPLETED_BATCH_STATUSES,
) -> NewsFetchBatch | None:
    statement = build_latest_news_fetch_batch_statement(
        scope=scope,
        cache_variant=cache_variant,
        ts_code=ts_code,
        statuses=statuses,
    ).limit(1)
    return (await session.execute(statement)).scalars().first()
