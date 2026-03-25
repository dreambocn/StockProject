from datetime import UTC, datetime

from sqlalchemy import Select, func, select, union_all
from sqlalchemy.orm import aliased

from app.models.news_event import NewsEvent


def _normalize_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def build_news_event_identity_key(row: NewsEvent) -> tuple[object, ...]:
    """构建事件身份键：优先使用 cluster_key，缺失时回退到稳定组合键。"""
    cluster_key = (row.cluster_key or "").strip()
    if cluster_key:
        return ("cluster", cluster_key)
    return (
        "fallback",
        row.scope.strip(),
        (row.ts_code or "").strip(),
        row.title.strip(),
        _normalize_datetime(row.published_at),
        (row.url or "").strip(),
    )


def latest_news_events_order_by(entity: object) -> tuple[object, ...]:
    """统一 latest 结果排序，保证分页稳定且跨数据库行为一致。"""
    return (
        entity.published_at.desc(),
        entity.fetched_at.desc(),
        entity.created_at.desc(),
        entity.id.desc(),
    )


def build_latest_news_events_statement(
    *,
    base_statement: Select[tuple[NewsEvent]],
    apply_default_order: bool = False,
) -> Select[tuple[NewsEvent]]:
    """
    基于基础过滤语句构建 latest 视图：
    - cluster_key 非空：按 cluster_key 分组取最新
    - cluster_key 为空：按稳定回退键分组取最新
    """
    base_subquery = base_statement.subquery("news_events_base")
    base_alias = aliased(NewsEvent, base_subquery)
    normalized_cluster_key = func.nullif(func.trim(base_alias.cluster_key), "")

    ranking_order = (
        base_alias.fetched_at.desc(),
        base_alias.created_at.desc(),
        base_alias.source_priority.desc(),
        base_alias.published_at.desc(),
        base_alias.id.desc(),
    )

    cluster_rank_statement = select(
        base_alias.id.label("id"),
        func.row_number()
        .over(
            partition_by=normalized_cluster_key,
            order_by=ranking_order,
        )
        .label("rn"),
    ).where(normalized_cluster_key.is_not(None))

    fallback_rank_statement = select(
        base_alias.id.label("id"),
        func.row_number()
        .over(
            partition_by=(
                base_alias.scope,
                func.coalesce(base_alias.ts_code, ""),
                base_alias.title,
                base_alias.published_at,
                func.coalesce(base_alias.url, ""),
            ),
            order_by=ranking_order,
        )
        .label("rn"),
    ).where(normalized_cluster_key.is_(None))

    ranked_subquery = (
        union_all(cluster_rank_statement, fallback_rank_statement)
    ).subquery("news_events_ranked")

    latest_statement = (
        select(base_alias)
        .join(ranked_subquery, base_alias.id == ranked_subquery.c.id)
        .where(ranked_subquery.c.rn == 1)
    )
    if apply_default_order:
        latest_statement = latest_statement.order_by(
            *latest_news_events_order_by(base_alias)
        )
    return latest_statement
