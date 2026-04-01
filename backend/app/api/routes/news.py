from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache.redis import get_redis_client
from app.core.logging import get_logger
from app.core.settings import get_settings
from app.db.session import get_db_session
from app.integrations.akshare_gateway import fetch_hot_news
from app.integrations.policy_gateway import (
    fetch_policy_events,
    list_policy_source_documents,
)
from app.integrations.tushare_gateway import TushareGateway
from app.schemas.news import (
    HotNewsItemResponse,
    MacroImpactProfileResponse,
    NewsEventResponse,
)
from app.services.news_cache_service import get_news_rows
from app.services.news_cache_version_service import (
    build_news_cache_version_key,
    format_news_cache_version,
    read_news_cache_version,
    resolve_news_cache_data_key,
    write_news_cache_version,
)
from app.services.news_fetch_batch_service import (
    NEWS_FETCH_STATUS_FAILED,
    NEWS_FETCH_STATUS_PARTIAL,
    NEWS_FETCH_STATUS_SUCCESS,
    create_news_fetch_batch,
    finalize_news_fetch_batch,
)
from app.services.news_mapper_service import (
    attach_dynamic_a_share_candidates,
    list_macro_impact_profiles,
    map_hot_news_rows,
    map_policy_news_rows,
    map_tushare_major_news_rows,
)
from app.services.market_theme_service import attach_theme_matches_to_profiles
from app.services.news_repository import (
    load_hot_news_rows_from_db,
    load_latest_hot_news_fetch_at,
    load_latest_policy_news_fetch_at,
    load_policy_news_rows,
    query_news_events,
    replace_hot_news_rows,
    replace_policy_news_rows,
)
from app.services.policy_projection_service import (
    project_policy_documents_to_news_events,
)
from app.services.stock_cache_service import (
    get_singleflight_lock,
    read_cached_model_rows,
    write_cached_model_rows,
)


router = APIRouter()
logger = get_logger(__name__)

HOT_NEWS_CACHE_PREFIX = "news:hot"
HOT_NEWS_CACHE_VARIANT = "global"
POLICY_NEWS_CACHE_PREFIX = "news:policy"
POLICY_NEWS_CACHE_VARIANT = "policy_source"

SUPPORTED_MACRO_TOPICS = {
    "all",
    "geopolitical_conflict",
    "monetary_policy",
    "commodity_supply",
    "regulation_policy",
    "other",
}
SUPPORTED_NEWS_SCOPES = {"hot", "stock", "policy"}
SUPPORTED_BATCH_MODES = {"latest", "all"}


def _normalize_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


async def _read_versioned_news_cache(
    *,
    base_cache_key: str,
    version_key: str,
    model_type: type[BaseModel],
    last_fetch_at: datetime | None,
    delete_on_decode_error: bool = False,
) -> list[BaseModel] | None:
    settings = get_settings()
    legacy_fallback_enabled = bool(
        getattr(settings, "news_cache_version_legacy_fallback_enabled", True)
    )
    legacy_fallback_seconds = int(
        getattr(settings, "news_cache_version_legacy_fallback_seconds", 3600)
    )
    version = await read_news_cache_version(
        version_key=version_key,
        redis_client_getter=get_redis_client,
    )
    if version is not None:
        # 命中版本号时直接读对应版本数据，避免与旧缓存混读。
        return await read_cached_model_rows(
            resolve_news_cache_data_key(
                base_cache_key=base_cache_key,
                version=version,
            ),
            model_type,
            delete_on_decode_error=delete_on_decode_error,
            redis_client_getter=get_redis_client,
        )

    if not legacy_fallback_enabled:
        return None

    # 仅在最近抓取时间仍在回退窗口内时允许读旧缓存。
    normalized_last_fetch_at = _normalize_datetime(last_fetch_at)
    if (
        normalized_last_fetch_at is not None
        and datetime.now(UTC) - normalized_last_fetch_at
        > timedelta(seconds=legacy_fallback_seconds)
    ):
        return None

    return await read_cached_model_rows(
        base_cache_key,
        model_type,
        delete_on_decode_error=delete_on_decode_error,
        redis_client_getter=get_redis_client,
    )


async def _write_versioned_news_cache(
    *,
    base_cache_key: str,
    version_key: str,
    rows: list[BaseModel],
    ttl_seconds: int,
) -> None:
    version = await read_news_cache_version(
        version_key=version_key,
        redis_client_getter=get_redis_client,
    )
    # 写入时如果版本为空，仍使用 resolve 结果回写，保持读写一致。
    await write_cached_model_rows(
        resolve_news_cache_data_key(
            base_cache_key=base_cache_key,
            version=version,
        ),
        rows,
        ttl_seconds=ttl_seconds,
        redis_client_getter=get_redis_client,
    )


@router.get("/news/hot", response_model=list[HotNewsItemResponse])
async def get_hot_news(
    limit: int = Query(default=50, ge=1, le=200),
    topic: str = Query(default="all"),
    session: AsyncSession = Depends(get_db_session),
) -> list[HotNewsItemResponse]:
    normalized_topic = topic.strip().lower() or "all"
    if normalized_topic not in SUPPORTED_MACRO_TOPICS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="invalid topic filter",
        )

    # 缓存 key 绑定主题与限制，确保不同过滤条件互不污染。
    cache_key = f"{HOT_NEWS_CACHE_PREFIX}:{normalized_topic}:{limit}"
    version_key = build_news_cache_version_key(
        scope="hot",
        cache_variant=HOT_NEWS_CACHE_VARIANT,
    )

    async def get_last_fetch_at() -> datetime | None:
        return await load_latest_hot_news_fetch_at(
            session=session,
            cache_variant=HOT_NEWS_CACHE_VARIANT,
        )

    async def read_cache(key: str) -> list[HotNewsItemResponse] | None:
        return await _read_versioned_news_cache(
            base_cache_key=key,
            version_key=version_key,
            model_type=HotNewsItemResponse,
            last_fetch_at=await get_last_fetch_at(),
            delete_on_decode_error=True,
        )

    async def write_cache(
        key: str,
        rows: list[HotNewsItemResponse],
        ttl_seconds: int,
    ) -> None:
        await _write_versioned_news_cache(
            base_cache_key=key,
            version_key=version_key,
            rows=rows,
            ttl_seconds=ttl_seconds,
        )

    async def load_from_db() -> list[HotNewsItemResponse]:
        return await load_hot_news_rows_from_db(
            session=session,
            cache_variant=HOT_NEWS_CACHE_VARIANT,
            topic=normalized_topic,
            limit=limit,
        )

    async def fetch_remote_and_persist() -> list[HotNewsItemResponse]:
        fetched_at = datetime.now(UTC)
        # 新批次必须先创建 batch 记录，方便追踪抓取质量与降级原因。
        batch = await create_news_fetch_batch(
            session,
            scope="hot",
            cache_variant=HOT_NEWS_CACHE_VARIANT,
            trigger_source="api.news.hot",
            fetched_at=fetched_at,
            started_at=fetched_at,
        )
        mapped: list[HotNewsItemResponse] = []
        provider_stats: list[dict[str, object]] = []
        degrade_reasons: list[str] = []
        raw_row_count = 0

        try:
            ak_rows = await fetch_hot_news()
            raw_row_count += len(ak_rows)
            mapped_ak_rows = map_hot_news_rows(ak_rows)
            mapped.extend(mapped_ak_rows)
            provider_stats.append(
                {
                    "provider": "akshare",
                    "status": "success",
                    "error_type": None,
                    "raw_count": len(ak_rows),
                    "mapped_count": len(mapped_ak_rows),
                    "persisted_count": len(mapped_ak_rows),
                }
            )
        except Exception as exc:
            # 关键降级：AkShare 失败时继续尝试其他来源，并记录可追踪日志。
            logger.warning(
                "event=hot_news_upstream_degraded provider=%s error_type=%s message=热点上游拉取失败",
                "akshare",
                type(exc).__name__,
            )
            provider_stats.append(
                {
                    "provider": "akshare",
                    "status": "failed",
                    "error_type": type(exc).__name__,
                    "raw_count": 0,
                    "mapped_count": 0,
                    "persisted_count": 0,
                }
            )
            degrade_reasons.append("hot.akshare_failed")

        settings = get_settings()
        if settings.tushare_token.strip():
            try:
                gateway = TushareGateway(settings.tushare_token)
                ts_rows = await gateway.fetch_major_news()
                raw_row_count += len(ts_rows)
                mapped_ts_rows = map_tushare_major_news_rows(ts_rows)
                mapped.extend(mapped_ts_rows)
                provider_stats.append(
                    {
                        "provider": "tushare",
                        "status": "success",
                        "error_type": None,
                        "raw_count": len(ts_rows),
                        "mapped_count": len(mapped_ts_rows),
                        "persisted_count": len(mapped_ts_rows),
                    }
                )
            except Exception as exc:
                # 关键降级：Tushare 失败时不阻断接口，回退到可用来源并记录日志。
                logger.warning(
                    "event=hot_news_upstream_degraded provider=%s error_type=%s message=热点上游拉取失败",
                    "tushare",
                    type(exc).__name__,
                )
                provider_stats.append(
                    {
                        "provider": "tushare",
                        "status": "failed",
                        "error_type": type(exc).__name__,
                        "raw_count": 0,
                        "mapped_count": 0,
                        "persisted_count": 0,
                    }
                )
                degrade_reasons.append("hot.tushare_failed")
        else:
            provider_stats.append(
                {
                    "provider": "tushare",
                    "status": "skipped",
                    "error_type": None,
                    "raw_count": 0,
                    "mapped_count": 0,
                    "persisted_count": 0,
                }
            )

        if not mapped:
            await finalize_news_fetch_batch(
                session,
                batch=batch,
                status=NEWS_FETCH_STATUS_FAILED,
                finished_at=datetime.now(UTC),
                row_count_raw=raw_row_count,
                row_count_mapped=0,
                row_count_persisted=0,
                provider_stats=provider_stats,
                degrade_reasons=degrade_reasons or ["mapping.empty_after_filter"],
                error_type="HTTPException",
                error_message="热点上游当前无可用结果",
            )
            await session.commit()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="hot news upstream unavailable",
            )

        # 关键流程：热点新闻按整批回源结果统一落库，后续不论页面展示还是 AI 分析，
        # 都可以直接从数据库按 topic/时间窗口检索，不必再次访问三方接口。
        await replace_hot_news_rows(
            session=session,
            cache_variant=HOT_NEWS_CACHE_VARIANT,
            fetched_at=fetched_at,
            batch_id=batch.id,
            rows=mapped,
        )
        await finalize_news_fetch_batch(
            session,
            batch=batch,
            status=(
                NEWS_FETCH_STATUS_PARTIAL if degrade_reasons else NEWS_FETCH_STATUS_SUCCESS
            ),
            finished_at=datetime.now(UTC),
            row_count_raw=raw_row_count,
            row_count_mapped=len(mapped),
            row_count_persisted=len(mapped),
            provider_stats=provider_stats,
            degrade_reasons=degrade_reasons,
        )
        await session.commit()
        await write_news_cache_version(
            version_key=version_key,
            version=format_news_cache_version(fetched_at=fetched_at),
            redis_client_getter=get_redis_client,
        )

        return await load_hot_news_rows_from_db(
            session=session,
            cache_variant=HOT_NEWS_CACHE_VARIANT,
            topic=normalized_topic,
            limit=limit,
        )

    return await get_news_rows(
        cache_key=cache_key,
        cache_ttl_seconds=get_settings().hot_news_cache_ttl_seconds,
        refresh_window_seconds=get_settings().hot_news_cache_ttl_seconds,
        now=datetime.now(UTC),
        read_cache=read_cache,
        write_cache=write_cache,
        load_from_db=load_from_db,
        get_last_fetch_at=get_last_fetch_at,
        fetch_remote_and_persist=fetch_remote_and_persist,
        get_singleflight_lock=get_singleflight_lock,
    )


@router.get("/news/events", response_model=list[NewsEventResponse])
async def get_news_events(
    scope: str | None = Query(default=None),
    ts_code: str | None = Query(default=None),
    topic: str | None = Query(default=None),
    batch_mode: str = Query(default="latest"),
    published_from: datetime | None = Query(default=None),
    published_to: datetime | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=200, ge=1, le=1000),
    session: AsyncSession = Depends(get_db_session),
) -> list[NewsEventResponse]:
    normalized_scope = scope.strip().lower() if scope else None
    if normalized_scope and normalized_scope not in SUPPORTED_NEWS_SCOPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="invalid scope filter",
        )

    normalized_ts_code = ts_code.strip().upper() if ts_code else None
    normalized_topic = topic.strip().lower() if topic else None
    normalized_batch_mode = batch_mode.strip().lower() or "latest"
    if normalized_topic and normalized_topic not in SUPPORTED_MACRO_TOPICS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="invalid topic filter",
        )
    if normalized_batch_mode not in SUPPORTED_BATCH_MODES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="invalid batch_mode filter",
        )

    if (
        published_from is not None
        and published_to is not None
        and published_from > published_to
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="published_from must be earlier than or equal to published_to",
        )

    offset = (page - 1) * page_size

    # 关键流程：该接口直接读取持久化新闻事件，给 AI 分析与离线回放提供稳定数据源，
    # 不触发任何三方回源；默认返回去重后的最新视图，需要全量历史时显式使用 batch_mode=all。
    return await query_news_events(
        session=session,
        scope=normalized_scope,
        ts_code=normalized_ts_code,
        topic=normalized_topic,
        published_from=published_from,
        published_to=published_to,
        limit=page_size,
        offset=offset,
        batch_mode=normalized_batch_mode,
    )


@router.get("/news/impact-map", response_model=list[MacroImpactProfileResponse])
async def get_macro_impact_map(
    topic: str = Query(default="all"),
    candidate_limit: int = Query(default=6, ge=1, le=20),
    candidate_evidence_limit: int = Query(default=3, ge=1, le=5),
    session: AsyncSession = Depends(get_db_session),
) -> list[MacroImpactProfileResponse]:
    normalized_topic = topic.strip().lower() or "all"
    if normalized_topic not in SUPPORTED_MACRO_TOPICS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="invalid topic filter",
        )

    # 关键流程：影响面板先返回稳定的规则映射，再补充数据库动态候选标的，保证可解释与可扩展兼容。
    profiles = list_macro_impact_profiles(normalized_topic)
    # 易误用边界：动态候选补充失败时要保留基础候选结果，避免路由层把已有候选误清空。
    try:
        if session is not None:
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
        logger.warning(
            "event=impact_map_dynamic_candidates_degraded error_type=%s message=候选增强失败，保留基础结果",
            type(exc).__name__,
        )

    return [MacroImpactProfileResponse.model_validate(item) for item in profiles]


@router.get("/news/policy", response_model=list[NewsEventResponse])
async def get_policy_news(
    limit: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session),
) -> list[NewsEventResponse]:
    cache_key = f"{POLICY_NEWS_CACHE_PREFIX}:{limit}"
    version_key = build_news_cache_version_key(
        scope="policy",
        cache_variant=POLICY_NEWS_CACHE_VARIANT,
    )

    async def get_last_fetch_at() -> datetime | None:
        return await load_latest_policy_news_fetch_at(session=session)

    async def read_cache(key: str) -> list[NewsEventResponse] | None:
        return await _read_versioned_news_cache(
            base_cache_key=key,
            version_key=version_key,
            model_type=NewsEventResponse,
            last_fetch_at=await get_last_fetch_at(),
        )

    async def write_cache(
        key: str,
        rows: list[NewsEventResponse],
        ttl_seconds: int,
    ) -> None:
        await _write_versioned_news_cache(
            base_cache_key=key,
            version_key=version_key,
            rows=rows,
            ttl_seconds=ttl_seconds,
        )

    async def load_from_db() -> list[NewsEventResponse]:
        return await load_policy_news_rows(session=session, limit=limit)

    async def fetch_remote_and_persist() -> list[NewsEventResponse]:
        fetched_at = datetime.now(UTC)
        batch = await create_news_fetch_batch(
            session,
            scope="policy",
            cache_variant=POLICY_NEWS_CACHE_VARIANT,
            trigger_source="api.news.policy",
            fetched_at=fetched_at,
            started_at=fetched_at,
        )

        documents = await list_policy_source_documents(session=session, limit=limit)
        if documents:
            projected_rows = await project_policy_documents_to_news_events(
                session,
                documents=documents,
                fetched_at=fetched_at,
                batch_id=batch.id,
            )
            await finalize_news_fetch_batch(
                session,
                batch=batch,
                status=NEWS_FETCH_STATUS_SUCCESS,
                finished_at=datetime.now(UTC),
                row_count_raw=len(documents),
                row_count_mapped=len(projected_rows),
                row_count_persisted=len(projected_rows),
                provider_stats=[
                    {
                        "provider": "policy_documents",
                        "status": "success",
                        "error_type": None,
                        "raw_count": len(documents),
                        "mapped_count": len(projected_rows),
                        "persisted_count": len(projected_rows),
                    }
                ],
                degrade_reasons=[],
            )
            await session.commit()
            await write_news_cache_version(
                version_key=version_key,
                version=format_news_cache_version(fetched_at=fetched_at),
                redis_client_getter=get_redis_client,
            )
            return await load_from_db()

        try:
            raw_rows = await fetch_policy_events()
        except Exception as exc:
            await finalize_news_fetch_batch(
                session,
                batch=batch,
                status=NEWS_FETCH_STATUS_FAILED,
                finished_at=datetime.now(UTC),
                row_count_raw=0,
                row_count_mapped=0,
                row_count_persisted=0,
                provider_stats=[
                    {
                        "provider": "policy_gateway",
                        "status": "failed",
                        "error_type": type(exc).__name__,
                        "raw_count": 0,
                        "mapped_count": 0,
                        "persisted_count": 0,
                    }
                ],
                degrade_reasons=["policy.fetch_failed"],
                error_type=type(exc).__name__,
                error_message="政策新闻上游抓取失败",
            )
            await session.commit()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="policy news upstream unavailable",
            ) from exc

        mapped = map_policy_news_rows(raw_rows)
        if not mapped:
            await finalize_news_fetch_batch(
                session,
                batch=batch,
                status=NEWS_FETCH_STATUS_FAILED,
                finished_at=datetime.now(UTC),
                row_count_raw=len(raw_rows),
                row_count_mapped=0,
                row_count_persisted=0,
                provider_stats=[
                    {
                        "provider": "policy_gateway",
                        "status": "success",
                        "error_type": None,
                        "raw_count": len(raw_rows),
                        "mapped_count": 0,
                        "persisted_count": 0,
                    }
                ],
                degrade_reasons=["mapping.empty_after_filter"],
                error_type=None,
                error_message="政策新闻映射后为空，回退到最近批次",
            )
            await session.commit()
            return await load_from_db()

        await replace_policy_news_rows(
            session=session,
            fetched_at=fetched_at,
            batch_id=batch.id,
            rows=mapped,
        )
        await finalize_news_fetch_batch(
            session,
            batch=batch,
            status=NEWS_FETCH_STATUS_SUCCESS,
            finished_at=datetime.now(UTC),
            row_count_raw=len(raw_rows),
            row_count_mapped=len(mapped),
            row_count_persisted=len(mapped),
            provider_stats=[
                {
                    "provider": "policy_gateway",
                    "status": "success",
                    "error_type": None,
                    "raw_count": len(raw_rows),
                    "mapped_count": len(mapped),
                    "persisted_count": len(mapped),
                }
            ],
            degrade_reasons=[],
        )
        await session.commit()
        await write_news_cache_version(
            version_key=version_key,
            version=format_news_cache_version(fetched_at=fetched_at),
            redis_client_getter=get_redis_client,
        )
        return await load_from_db()

    return await get_news_rows(
        cache_key=cache_key,
        cache_ttl_seconds=get_settings().policy_news_cache_ttl_seconds,
        refresh_window_seconds=get_settings().policy_news_cache_ttl_seconds,
        now=datetime.now(UTC),
        read_cache=read_cache,
        write_cache=write_cache,
        load_from_db=load_from_db,
        get_last_fetch_at=get_last_fetch_at,
        fetch_remote_and_persist=fetch_remote_and_persist,
        get_singleflight_lock=get_singleflight_lock,
    )
