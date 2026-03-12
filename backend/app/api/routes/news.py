from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.integrations.akshare_gateway import fetch_hot_news
from app.schemas.news import HotNewsItemResponse, MacroImpactProfileResponse
from app.services.news_mapper_service import (
    attach_dynamic_a_share_candidates,
    list_macro_impact_profiles,
    map_hot_news_rows,
)


router = APIRouter()

SUPPORTED_MACRO_TOPICS = {
    "all",
    "geopolitical_conflict",
    "monetary_policy",
    "commodity_supply",
    "regulation_policy",
    "other",
}


@router.get("/news/hot", response_model=list[HotNewsItemResponse])
async def get_hot_news(
    limit: int = Query(default=50, ge=1, le=200),
    topic: str = Query(default="all"),
) -> list[HotNewsItemResponse]:
    try:
        rows = await fetch_hot_news()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="hot news upstream unavailable",
        ) from exc

    mapped = map_hot_news_rows(rows)

    normalized_topic = topic.strip().lower() or "all"
    if normalized_topic not in SUPPORTED_MACRO_TOPICS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="invalid topic filter",
        )

    # 关键业务分支：仅当用户显式选择 topic 时才过滤，默认 all 保留完整热点流。
    if normalized_topic != "all":
        mapped = [item for item in mapped if item.macro_topic == normalized_topic]

    return mapped[:limit]


@router.get("/news/impact-map", response_model=list[MacroImpactProfileResponse])
async def get_macro_impact_map(
    topic: str = Query(default="all"),
    candidate_limit: int = Query(default=6, ge=1, le=20),
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
    # 易误用边界：动态候选依赖股票基础库，若数据库查询失败则降级为空候选，避免影响主接口可用性。
    try:
        if session is not None:
            profiles = await attach_dynamic_a_share_candidates(
                session=session,
                profiles=profiles,
                per_topic_limit=candidate_limit,
            )
    except Exception:
        for profile in profiles:
            profile["a_share_candidates"] = []

    return [MacroImpactProfileResponse.model_validate(item) for item in profiles]
