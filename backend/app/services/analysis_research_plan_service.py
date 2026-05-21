from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import get_settings
from app.services.analysis_event_selection_service import select_generation_analysis_events
from app.services.analysis_limits import resolve_generation_event_limit
from app.services.analysis_orchestrator_service import (
    ANALYSIS_MODE_FUNCTIONAL_MULTI_AGENT,
    normalize_analysis_mode,
)
from app.services.analysis_repository import (
    load_recent_news_events,
    load_stock_instrument,
)


class ResearchPlanNotFoundError(Exception):
    """研究计划预览所需基础数据不存在。"""


def count_events_by_kind(events: list[object]) -> dict[str, int]:
    counts = {
        "policy": 0,
        "announcement": 0,
        "stock": 0,
        "hot": 0,
        "news": 0,
    }
    for event in events:
        scope = str(getattr(event, "scope", "") or "").lower()
        event_type = str(getattr(event, "event_type", "") or "").lower()
        source = str(getattr(event, "source", "") or "").lower()
        if scope == "policy" or event_type == "policy":
            counts["policy"] += 1
        elif source == "cninfo_announcement" or event_type == "announcement":
            counts["announcement"] += 1
        elif scope == "stock":
            counts["stock"] += 1
        elif scope == "hot":
            counts["hot"] += 1
        else:
            counts["news"] += 1
    return counts


async def build_research_plan_payload(
    session: AsyncSession,
    ts_code: str,
    *,
    topic: str | None,
    event_id: str | None,
    use_web_search: bool,
    analysis_mode: str = "single",
) -> dict[str, object]:
    normalized_ts_code = ts_code.strip().upper()
    instrument = await load_stock_instrument(session, normalized_ts_code)
    if instrument is None:
        raise ResearchPlanNotFoundError("stock not found")

    settings = get_settings()
    generation_limit = resolve_generation_event_limit(settings, 20)
    candidate_pool_limit = max(
        generation_limit * settings.analysis_generation_candidate_pool_multiplier,
        generation_limit + 20,
    )
    events = await load_recent_news_events(
        session,
        normalized_ts_code,
        topic=topic,
        anchor_event_id=event_id,
        published_from=None,
        published_to=None,
        limit=generation_limit,
        candidate_limit=candidate_pool_limit,
    )
    selected_events = select_generation_analysis_events(
        events,
        anchor_event_id=event_id,
        total_limit=generation_limit,
        stock_quota=settings.analysis_generation_stock_quota,
        policy_quota=settings.analysis_generation_policy_quota,
        hot_quota=settings.analysis_generation_hot_quota,
    )
    counts = count_events_by_kind(selected_events)
    focus_buckets = [
        {"key": "policy", "label": "政策原文", "count": counts["policy"]},
        {"key": "announcement", "label": "公告事件", "count": counts["announcement"]},
        {"key": "stock", "label": "个股事件", "count": counts["stock"]},
        {"key": "hot", "label": "热点事件", "count": counts["hot"]},
        {"key": "market_data", "label": "行情数据", "count": 1},
    ]
    focus_buckets = [item for item in focus_buckets if item["count"] > 0]
    if not focus_buckets:
        focus_buckets = [{"key": "market_data", "label": "行情数据", "count": 1}]

    priority_questions = [
        "锚点事件是否足以解释近期波动？" if event_id else "近期主要驱动事件是什么？",
        "结构化事件、政策原文与行情窗口是否相互印证？",
        "现有证据是否存在来源不足、时间滞后或结论冲突？",
    ]
    if use_web_search:
        priority_questions.append("联网引用能否补足公开来源和发布时间？")

    estimated_steps = [
        "确认股票、主题与锚点事件范围",
        "整理结构化事件、政策原文与行情窗口",
        "按证据强弱生成假设并进行风险审计",
        "输出核心判断、风险提示和来源清单",
    ]
    if analysis_mode == ANALYSIS_MODE_FUNCTIONAL_MULTI_AGENT:
        estimated_steps.insert(2, "分配研究规划、取证、假设、质询和裁决角色")

    source_scope = {
        "event_count": len(selected_events),
        "policy_count": counts["policy"],
        "announcement_count": counts["announcement"],
        "stock_event_count": counts["stock"],
        "hot_event_count": counts["hot"],
        "web_search": use_web_search,
        "anchor_event_id": event_id,
        "topic": topic,
    }
    summary = (
        f"将围绕 {normalized_ts_code} "
        f"{('的 ' + topic) if topic else '的近期事件'}，先核对"
        f"{len(selected_events)} 条候选证据，再生成可追溯结论。"
    )
    return {
        "ts_code": normalized_ts_code,
        "summary": summary,
        "focus_buckets": focus_buckets,
        "priority_questions": priority_questions,
        "source_scope": source_scope,
        "web_search_recommended": bool(use_web_search or counts["policy"] == 0),
        "estimated_steps": estimated_steps,
        "analysis_mode": normalize_analysis_mode(
            analysis_mode,
            trigger_source="manual",
        ),
    }
