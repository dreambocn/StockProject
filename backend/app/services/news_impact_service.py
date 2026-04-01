from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.settings import get_settings
from app.models.market_theme import MarketTheme
from app.models.market_theme_membership import MarketThemeMembership
from app.schemas.news import MacroImpactProfileResponse
from app.services.market_theme_service import attach_theme_matches_to_profiles
from app.services.job_service import (
    JOB_STATUS_FAILED,
    JOB_STATUS_RUNNING,
    JOB_STATUS_SUCCESS,
    create_job_run,
    finish_job_run,
)
from app.services.news_cache_version_service import (
    read_news_cache_version,
    resolve_news_cache_data_key,
    write_news_cache_version,
)
from app.services.news_repository import (
    load_latest_candidate_evidence_fetch_at,
    load_latest_hot_news_fetch_at,
)
from app.services.news_mapper_service import (
    attach_dynamic_a_share_candidates,
    list_macro_impact_profiles,
)
from app.services.stock_cache_service import (
    get_singleflight_lock,
    read_cached_model_rows,
    write_cached_model_rows,
)


LOGGER = get_logger(__name__)
IMPACT_MAP_CACHE_PREFIX = "news:impact-map"
DEFAULT_IMPACT_CACHE_VARIANT = "default"
DEFAULT_IMPACT_CANDIDATE_LIMIT = 6
DEFAULT_IMPACT_CANDIDATE_EVIDENCE_LIMIT = 3
DEFAULT_IMPACT_TOPICS = (
    "all",
    "geopolitical_conflict",
    "monetary_policy",
    "commodity_supply",
    "regulation_policy",
    "other",
)


def _normalize_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _format_version_part(value: datetime | None) -> str:
    normalized = _normalize_datetime(value)
    if normalized is None:
        return "none"
    return normalized.strftime("%Y%m%d%H%M%S")


def _build_impact_cache_key(*, topic: str, cache_variant: str = DEFAULT_IMPACT_CACHE_VARIANT) -> str:
    normalized_topic = topic.strip().lower() or "all"
    normalized_variant = cache_variant.strip().lower() or DEFAULT_IMPACT_CACHE_VARIANT
    return f"{IMPACT_MAP_CACHE_PREFIX}:{normalized_variant}:{normalized_topic}"


def _build_impact_cache_version_key(
    *,
    topic: str,
    cache_variant: str = DEFAULT_IMPACT_CACHE_VARIANT,
) -> str:
    return f"{_build_impact_cache_key(topic=topic, cache_variant=cache_variant)}:version"


async def load_latest_theme_snapshot_at(session: AsyncSession) -> datetime | None:
    membership_updated_at = (
        await session.execute(select(func.max(MarketThemeMembership.updated_at)))
    ).scalar_one_or_none()
    theme_updated_at = (
        await session.execute(select(func.max(MarketTheme.updated_at)))
    ).scalar_one_or_none()
    normalized_values = [
        value
        for value in (
            _normalize_datetime(membership_updated_at),
            _normalize_datetime(theme_updated_at),
        )
        if value is not None
    ]
    return max(normalized_values) if normalized_values else None


async def build_news_impact_source_version(session: AsyncSession) -> str:
    latest_hot_news_at = await load_latest_hot_news_fetch_at(
        session=session,
        cache_variant="global",
    )
    latest_hot_search_at = await load_latest_candidate_evidence_fetch_at(
        session=session,
        evidence_kind="hot_search",
    )
    latest_research_report_at = await load_latest_candidate_evidence_fetch_at(
        session=session,
        evidence_kind="research_report",
    )
    latest_evidence_at = max(
        [
            value
            for value in (
                _normalize_datetime(latest_hot_search_at),
                _normalize_datetime(latest_research_report_at),
            )
            if value is not None
        ],
        default=None,
    )
    latest_theme_at = await load_latest_theme_snapshot_at(session)
    return (
        f"hot={_format_version_part(latest_hot_news_at)}"
        f"|evidence={_format_version_part(latest_evidence_at)}"
        f"|theme={_format_version_part(latest_theme_at)}"
    )


async def build_news_impact_profiles(
    *,
    session: AsyncSession,
    topic: str,
    candidate_limit: int = DEFAULT_IMPACT_CANDIDATE_LIMIT,
    candidate_evidence_limit: int = DEFAULT_IMPACT_CANDIDATE_EVIDENCE_LIMIT,
    degrade_on_enhancement_error: bool = True,
) -> list[MacroImpactProfileResponse]:
    # 关键流程：影响面板先返回稳定的规则映射，再补充数据库动态候选标的，保证可解释与可扩展兼容。
    profiles = list_macro_impact_profiles(topic)
    try:
        profiles = await attach_dynamic_a_share_candidates(
            session=session,
            profiles=profiles,
            per_topic_limit=candidate_limit,
            evidence_item_limit=candidate_evidence_limit,
        )
        profiles = await attach_theme_matches_to_profiles(
            session,
            profiles=profiles,
        )
    except Exception as exc:
        # 候选增强失败时保留基础结果，避免接口因为附加信息缺失而整体失败。
        LOGGER.warning(
            "event=impact_map_dynamic_candidates_degraded error_type=%s message=候选增强失败，保留基础结果",
            type(exc).__name__,
        )
        if not degrade_on_enhancement_error:
            raise
    return [MacroImpactProfileResponse.model_validate(item) for item in profiles]


async def get_cached_news_impact_profiles(
    *,
    session: AsyncSession,
    topic: str,
    cache_variant: str = DEFAULT_IMPACT_CACHE_VARIANT,
    force_refresh: bool = False,
) -> tuple[list[MacroImpactProfileResponse], str]:
    base_cache_key = _build_impact_cache_key(topic=topic, cache_variant=cache_variant)
    version_key = _build_impact_cache_version_key(topic=topic, cache_variant=cache_variant)
    source_version = await build_news_impact_source_version(session)
    previous_rows: list[MacroImpactProfileResponse] | None = None

    if not force_refresh:
        current_version = await read_news_cache_version(version_key=version_key)
        if current_version:
            previous_rows = await read_cached_model_rows(
                resolve_news_cache_data_key(
                    base_cache_key=base_cache_key,
                    version=current_version,
                ),
                MacroImpactProfileResponse,
            )
            if current_version == source_version and previous_rows is not None:
                return previous_rows, source_version

    lock = await get_singleflight_lock(f"{base_cache_key}:build")
    async with lock:
        current_version = await read_news_cache_version(version_key=version_key)
        if current_version:
            previous_rows = await read_cached_model_rows(
                resolve_news_cache_data_key(
                    base_cache_key=base_cache_key,
                    version=current_version,
                ),
                MacroImpactProfileResponse,
            )
            if (
                not force_refresh
                and current_version == source_version
                and previous_rows is not None
            ):
                return previous_rows, source_version

        try:
            rows = await build_news_impact_profiles(
                session=session,
                topic=topic,
                degrade_on_enhancement_error=previous_rows is None,
            )
            await write_cached_model_rows(
                resolve_news_cache_data_key(
                    base_cache_key=base_cache_key,
                    version=source_version,
                ),
                rows,
                ttl_seconds=get_settings().hot_news_cache_ttl_seconds,
            )
            await write_news_cache_version(
                version_key=version_key,
                version=source_version,
            )
            return rows, source_version
        except Exception as exc:
            # 关键降级：新版本快照构建失败时优先回退上一版成功快照，避免热点页影响面板整体变空。
            if previous_rows is not None:
                LOGGER.warning(
                    "event=news_impact_snapshot_rebuild_failed topic=%s error_type=%s message=影响快照重建失败，回退上一版快照",
                    topic,
                    type(exc).__name__,
                )
                return previous_rows, source_version
            raise


async def refresh_news_impact_snapshots(
    session: AsyncSession,
    *,
    trigger_source: str,
    topics: tuple[str, ...] = DEFAULT_IMPACT_TOPICS,
) -> dict[str, object]:
    source_version = await build_news_impact_source_version(session)
    job = await create_job_run(
        session,
        job_type="news_impact_refresh",
        status=JOB_STATUS_RUNNING,
        trigger_source=trigger_source,
        resource_type="news_impact_map",
        resource_key=DEFAULT_IMPACT_CACHE_VARIANT,
        summary="热点影响快照刷新中",
        metrics_json={
            "source_version": source_version,
            "refreshed_topic_count": 0,
        },
    )

    refreshed_topic_count = 0
    try:
        for topic in topics:
            await get_cached_news_impact_profiles(
                session=session,
                topic=topic,
                force_refresh=True,
            )
            refreshed_topic_count += 1

        await finish_job_run(
            session,
            job=job,
            status=JOB_STATUS_SUCCESS,
            summary="热点影响快照刷新完成",
            metrics_json={
                "source_version": source_version,
                "refreshed_topic_count": refreshed_topic_count,
            },
        )
        await session.commit()
        return {
            "job_id": job.id,
            "job_type": "news_impact_refresh",
            "status": JOB_STATUS_SUCCESS,
            "source_version": source_version,
            "refreshed_topic_count": refreshed_topic_count,
        }
    except Exception as exc:
        await finish_job_run(
            session,
            job=job,
            status=JOB_STATUS_FAILED,
            summary="热点影响快照刷新失败",
            metrics_json={
                "source_version": source_version,
                "refreshed_topic_count": refreshed_topic_count,
            },
            error_type=type(exc).__name__,
            error_message=str(exc),
        )
        await session.commit()
        raise
