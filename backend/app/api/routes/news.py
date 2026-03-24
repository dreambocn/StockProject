from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache.redis import get_redis_client
from app.core.logging import get_logger
from app.core.settings import get_settings
from app.db.session import get_db_session
from app.integrations.akshare_gateway import fetch_hot_news
from app.integrations.policy_gateway import fetch_policy_events
from app.integrations.tushare_gateway import TushareGateway
from app.schemas.news import (
    HotNewsItemResponse,
    MacroImpactProfileResponse,
    NewsEventResponse,
)
from app.services.news_cache_service import get_news_rows
from app.services.news_mapper_service import (
    attach_dynamic_a_share_candidates,
    list_macro_impact_profiles,
    map_hot_news_rows,
    map_policy_news_rows,
    map_tushare_major_news_rows,
)
from app.services.news_repository import (
    load_hot_news_rows_from_db,
    load_latest_hot_news_fetch_at,
    load_policy_news_rows,
    query_news_events,
    replace_hot_news_rows,
    replace_policy_news_rows,
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

    cache_key = f"{HOT_NEWS_CACHE_PREFIX}:{normalized_topic}:{limit}"

    async def read_cache(key: str) -> list[HotNewsItemResponse] | None:
        return await read_cached_model_rows(
            key,
            HotNewsItemResponse,
            delete_on_decode_error=True,
            redis_client_getter=get_redis_client,
        )

    async def write_cache(
        key: str,
        rows: list[HotNewsItemResponse],
        ttl_seconds: int,
    ) -> None:
        await write_cached_model_rows(
            key,
            rows,
            ttl_seconds=ttl_seconds,
            redis_client_getter=get_redis_client,
        )

    async def load_from_db() -> list[HotNewsItemResponse]:
        return await load_hot_news_rows_from_db(
            session=session,
            cache_variant=HOT_NEWS_CACHE_VARIANT,
            topic=normalized_topic,
            limit=limit,
        )

    async def get_last_fetch_at() -> datetime | None:
        return await load_latest_hot_news_fetch_at(
            session=session,
            cache_variant=HOT_NEWS_CACHE_VARIANT,
        )

    async def fetch_remote_and_persist() -> list[HotNewsItemResponse]:
        mapped: list[HotNewsItemResponse] = []

        try:
            ak_rows = await fetch_hot_news()
            mapped.extend(map_hot_news_rows(ak_rows))
        except Exception as exc:
            # 关键降级：AkShare 失败时继续尝试其他来源，并记录可追踪日志。
            logger.warning(
                "event=hot_news_upstream_degraded provider=%s error_type=%s message=热点上游拉取失败",
                "akshare",
                type(exc).__name__,
            )

        settings = get_settings()
        if settings.tushare_token.strip():
            try:
                gateway = TushareGateway(settings.tushare_token)
                ts_rows = await gateway.fetch_major_news()
                mapped.extend(map_tushare_major_news_rows(ts_rows))
            except Exception as exc:
                # 关键降级：Tushare 失败时不阻断接口，回退到可用来源并记录日志。
                logger.warning(
                    "event=hot_news_upstream_degraded provider=%s error_type=%s message=热点上游拉取失败",
                    "tushare",
                    type(exc).__name__,
                )

        if not mapped:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="hot news upstream unavailable",
            )

        fetched_at = datetime.now(UTC)
        # 关键流程：热点新闻按整批回源结果统一落库，后续不论页面展示还是 AI 分析，
        # 都可以直接从数据库按 topic/时间窗口检索，不必再次访问三方接口。
        await replace_hot_news_rows(
            session=session,
            cache_variant=HOT_NEWS_CACHE_VARIANT,
            fetched_at=fetched_at,
            rows=mapped,
        )
        await session.commit()

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
    except Exception as exc:
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
    raw_rows = await fetch_policy_events()
    mapped = map_policy_news_rows(raw_rows)
    if mapped:
        await replace_policy_news_rows(
            session=session,
            fetched_at=datetime.now(UTC),
            rows=mapped,
        )
        await session.commit()
        return mapped[:limit]

    return await load_policy_news_rows(session=session, limit=limit)
