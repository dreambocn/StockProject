from __future__ import annotations

from datetime import UTC, datetime
from typing import Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.settings import Settings, get_settings
from app.integrations.policy_provider import PolicyProvider
from app.integrations.policy_provider_registry import build_policy_provider_registry
from app.services.job_service import (
    JOB_STATUS_FAILED,
    JOB_STATUS_PARTIAL,
    JOB_STATUS_RUNNING,
    JOB_STATUS_SUCCESS,
    create_job_run,
    finish_job_run,
)
from app.services.policy_dedup_service import dedupe_policy_documents
from app.services.policy_normalization_service import normalize_policy_seed
from app.services.policy_repository import upsert_policy_documents


LOGGER = get_logger(__name__)


def _normalize_datetime(value: datetime | None) -> datetime:
    resolved = value or datetime.now(UTC)
    if resolved.tzinfo is None:
        return resolved.replace(tzinfo=UTC)
    return resolved.astimezone(UTC)


def _resolve_policy_providers(
    *,
    providers: Iterable[PolicyProvider] | None,
    settings: Settings,
) -> list[PolicyProvider]:
    if providers is not None:
        return list(providers)
    return build_policy_provider_registry(settings)


async def sync_policy_documents(
    session: AsyncSession,
    *,
    trigger_source: str,
    force_refresh: bool,
    providers: Iterable[PolicyProvider] | None = None,
    now: datetime | None = None,
    settings: Settings | None = None,
) -> dict[str, object]:
    resolved_settings = settings or get_settings()
    resolved_now = _normalize_datetime(now)
    provider_list = _resolve_policy_providers(
        providers=providers,
        settings=resolved_settings,
    )

    job = await create_job_run(
        session,
        job_type="policy_sync",
        status=JOB_STATUS_RUNNING,
        trigger_source=trigger_source.strip() or "unknown",
        resource_type="policy_document",
        resource_key="all",
        summary="政策同步执行中",
        payload_json={
            "force_refresh": force_refresh,
            "provider_count": len(provider_list),
        },
        started_at=resolved_now,
        heartbeat_at=resolved_now,
    )

    raw_count = 0
    normalized_count = 0
    failed_provider_count = 0
    successful_providers: list[str] = []
    failed_providers: list[str] = []
    provider_stats: list[dict[str, object]] = []
    normalized_documents = []

    try:
        if not resolved_settings.policy_sync_enabled and not force_refresh:
            metrics = {
                "provider_count": len(provider_list),
                "raw_count": 0,
                "normalized_count": 0,
                "inserted_count": 0,
                "updated_count": 0,
                "deduped_count": 0,
                "failed_provider_count": 0,
                "successful_provider_count": 0,
                "successful_providers": [],
                "failed_providers": [],
                "provider_stats": [],
            }
            await finish_job_run(
                session,
                job=job,
                status=JOB_STATUS_SUCCESS,
                summary="政策同步已禁用，跳过执行",
                metrics_json=metrics,
                finished_at=resolved_now,
            )
            await session.commit()
            return {
                **metrics,
                "status": JOB_STATUS_SUCCESS,
                "job_id": job.id,
                "document_ids": [],
            }

        for provider in provider_list:
            provider_source = (
                str(getattr(provider, "source", provider.__class__.__name__)).strip()
                or provider.__class__.__name__.lower()
            )
            try:
                raw_documents = await provider.fetch_documents(now=resolved_now)
                limited_documents = raw_documents[
                    : max(0, resolved_settings.policy_source_max_items_per_provider)
                ]
                raw_count += len(limited_documents)
                provider_normalized_count = 0
                for seed in limited_documents:
                    normalized_documents.append(normalize_policy_seed(seed))
                    provider_normalized_count += 1
                normalized_count += provider_normalized_count
                provider_stats.append(
                    {
                        "provider": provider_source,
                        "status": "success",
                        "error_type": None,
                        "raw_count": len(limited_documents),
                        "normalized_count": provider_normalized_count,
                    }
                )
                successful_providers.append(provider_source)
            except Exception as exc:
                failed_provider_count += 1
                failed_providers.append(provider_source)
                provider_stats.append(
                    {
                        "provider": provider_source,
                        "status": "failed",
                        "error_type": type(exc).__name__,
                        "raw_count": 0,
                        "normalized_count": 0,
                    }
                )

        dedup_result = dedupe_policy_documents(normalized_documents)
        repository_result = await upsert_policy_documents(
            session,
            documents=dedup_result.documents,
            sync_job_id=job.id,
        )
        job_status = JOB_STATUS_SUCCESS
        summary = "政策同步完成"
        if failed_provider_count > 0:
            job_status = JOB_STATUS_PARTIAL
            summary = "政策同步部分完成"
        if provider_list and failed_provider_count == len(provider_list) and not dedup_result.documents:
            job_status = JOB_STATUS_FAILED
            summary = "政策同步失败"

        metrics = {
            "provider_count": len(provider_list),
            "raw_count": raw_count,
            "normalized_count": normalized_count,
            "inserted_count": repository_result.inserted_count,
            "updated_count": repository_result.updated_count,
            "deduped_count": dedup_result.deduped_count,
            "failed_provider_count": failed_provider_count,
            "successful_provider_count": len(successful_providers),
            "successful_providers": successful_providers,
            "failed_providers": failed_providers,
            "provider_stats": provider_stats,
        }
        await finish_job_run(
            session,
            job=job,
            status=job_status,
            summary=summary,
            metrics_json=metrics,
            finished_at=resolved_now,
        )
        await session.commit()
        LOGGER.info(
            "event=policy_sync_finished job_id=%s status=%s provider_count=%s raw_count=%s normalized_count=%s inserted_count=%s updated_count=%s deduped_count=%s failed_provider_count=%s message=政策同步完成",
            job.id,
            job_status,
            len(provider_list),
            raw_count,
            normalized_count,
            repository_result.inserted_count,
            repository_result.updated_count,
            dedup_result.deduped_count,
            failed_provider_count,
        )
        return {
            **metrics,
            "status": job_status,
            "job_id": job.id,
            "document_ids": [row.id for row in repository_result.documents],
        }
    except Exception as exc:
        metrics = {
            "provider_count": len(provider_list),
            "raw_count": raw_count,
            "normalized_count": normalized_count,
            "inserted_count": 0,
            "updated_count": 0,
            "deduped_count": 0,
            "failed_provider_count": failed_provider_count,
            "successful_provider_count": len(successful_providers),
            "successful_providers": successful_providers,
            "failed_providers": failed_providers,
            "provider_stats": provider_stats,
        }
        await finish_job_run(
            session,
            job=job,
            status=JOB_STATUS_FAILED,
            summary="政策同步失败",
            metrics_json=metrics,
            error_type=type(exc).__name__,
            error_message=str(exc),
            finished_at=_normalize_datetime(None),
        )
        await session.commit()
        raise
