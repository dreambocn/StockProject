from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from app.models.news_event import NewsEvent


MIN_DATETIME = datetime.min.replace(tzinfo=UTC)


def _normalize_datetime(value: object | None) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _resolve_event_value(event: NewsEvent | Mapping[str, Any], field_name: str) -> object | None:
    if isinstance(event, NewsEvent):
        return getattr(event, field_name)
    return event.get(field_name)


def build_analysis_event_logical_key(
    event: NewsEvent | Mapping[str, Any],
) -> tuple[object, ...]:
    """构建分析事件去重键，优先使用 cluster_key，其次回退到稳定组合键。"""
    cluster_key = str(_resolve_event_value(event, "cluster_key") or "").strip()
    if cluster_key:
        return ("cluster", cluster_key)
    return (
        "fallback",
        str(_resolve_event_value(event, "scope") or "").strip(),
        str(_resolve_event_value(event, "ts_code") or "").strip(),
        str(_resolve_event_value(event, "title") or "").strip(),
        _normalize_datetime(_resolve_event_value(event, "published_at")),
        str(_resolve_event_value(event, "url") or "").strip(),
    )


def _build_generation_sort_key(
    event: NewsEvent,
    *,
    anchor_event: NewsEvent | None,
) -> tuple[object, ...]:
    # 排序优先保证同标的/同主题靠前，再按时间与来源权重排序。
    same_ts_code = (
        1
        if anchor_event
        and anchor_event.ts_code
        and event.ts_code
        and anchor_event.ts_code == event.ts_code
        else 0
    )
    same_macro_topic = (
        1
        if anchor_event
        and anchor_event.macro_topic
        and event.macro_topic
        and anchor_event.macro_topic == event.macro_topic
        else 0
    )
    return (
        same_ts_code,
        same_macro_topic,
        _normalize_datetime(event.published_at) or MIN_DATETIME,
        _normalize_datetime(event.fetched_at) or MIN_DATETIME,
        _normalize_datetime(event.created_at) or MIN_DATETIME,
        int(event.source_priority or 0),
        event.id,
    )


def _scope_bucket(scope: object | None) -> str | None:
    normalized_scope = str(scope or "").strip()
    if normalized_scope in {"stock", "policy", "hot"}:
        return normalized_scope
    return None


def _dedupe_preserving_order(
    events: Sequence[NewsEvent | Mapping[str, Any]],
    *,
    anchor_event_id: str | None,
) -> list[NewsEvent | Mapping[str, Any]]:
    anchor_event = next(
        (
            event
            for event in events
            if str(_resolve_event_value(event, "id") or _resolve_event_value(event, "event_id") or "")
            == (anchor_event_id or "")
        ),
        None,
    )
    deduped: list[NewsEvent | Mapping[str, Any]] = []
    seen_keys: set[tuple[object, ...]] = set()
    if anchor_event is not None:
        # 锚点事件必须保留在首位，保证摘要上下文稳定。
        anchor_key = build_analysis_event_logical_key(anchor_event)
        deduped.append(anchor_event)
        seen_keys.add(anchor_key)

    for event in events:
        event_id = str(
            _resolve_event_value(event, "id")
            or _resolve_event_value(event, "event_id")
            or ""
        )
        if anchor_event_id and event_id == anchor_event_id:
            continue
        event_key = build_analysis_event_logical_key(event)
        if event_key in seen_keys:
            continue
        deduped.append(event)
        seen_keys.add(event_key)
    return deduped


def select_generation_analysis_events(
    events: Sequence[NewsEvent],
    *,
    anchor_event_id: str | None,
    total_limit: int,
    stock_quota: int,
    policy_quota: int,
    hot_quota: int,
) -> list[NewsEvent]:
    """按锚点优先和分桶配额裁剪分析输入事件。"""
    if total_limit <= 0:
        return []

    anchor_event = next((event for event in events if event.id == anchor_event_id), None)
    ranked_events = sorted(
        events,
        key=lambda event: _build_generation_sort_key(event, anchor_event=anchor_event),
        reverse=True,
    )
    deduped_events = _dedupe_preserving_order(
        ranked_events,
        anchor_event_id=anchor_event_id,
    )

    selected: list[NewsEvent] = []
    seen_event_ids: set[str] = set()
    used_quota = {"stock": 0, "policy": 0, "hot": 0}
    quota_map = {"stock": stock_quota, "policy": policy_quota, "hot": hot_quota}

    if anchor_event is not None:
        selected.append(anchor_event)
        seen_event_ids.add(anchor_event.id)
        anchor_bucket = _scope_bucket(anchor_event.scope)
        if anchor_bucket is not None:
            used_quota[anchor_bucket] += 1

    # 按分桶配额先选足 stock/policy/hot，保证输入结构稳定。
    for bucket in ("stock", "policy", "hot"):
        for event in deduped_events:
            if event.id in seen_event_ids:
                continue
            if _scope_bucket(event.scope) != bucket:
                continue
            if used_quota[bucket] >= quota_map[bucket]:
                continue
            selected.append(event)
            seen_event_ids.add(event.id)
            used_quota[bucket] += 1
            if len(selected) >= total_limit:
                return selected[:total_limit]

    for event in deduped_events:
        if event.id in seen_event_ids:
            continue
        selected.append(event)
        seen_event_ids.add(event.id)
        if len(selected) >= total_limit:
            break

    return selected[:total_limit]


def select_summary_analysis_events(
    events: Sequence[Mapping[str, Any]],
    *,
    anchor_event_id: str | None,
    total_limit: int,
) -> list[dict[str, Any]]:
    """对摘要展示事件做逻辑去重，并在需要时保留指定锚点事件。"""
    if total_limit <= 0:
        return []

    deduped_events = _dedupe_preserving_order(events, anchor_event_id=anchor_event_id)
    return [dict(event) for event in deduped_events[:total_limit]]
