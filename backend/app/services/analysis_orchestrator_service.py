from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import UTC, date, datetime, time
from decimal import Decimal
from enum import Enum
import json
import re
from typing import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.factor_weight_service import FactorWeight
from app.services.llm_client_service import LlmTextResult, generate_llm_result, generate_streamed_llm_result

ANALYSIS_MODE_SINGLE = "single"
ANALYSIS_MODE_FUNCTIONAL_MULTI_AGENT = "functional_multi_agent"
FUNCTIONAL_MULTI_AGENT_ORCHESTRATOR_VERSION = "functional-multi-agent-v1"
FUNCTIONAL_PROMPT_VERSION_PREFIX = "fma-v1"
ROLE_EVENT = Callable[[str, dict[str, object]], Awaitable[None]]
TEXT_EVENT = Callable[[str], Awaitable[None]]


@dataclass
class FunctionalRoleResult:
    role_key: str
    role_label: str
    status: str
    sort_order: int
    summary: str | None
    output_payload: dict[str, object]
    used_web_search: bool
    web_search_status: str
    web_sources: list[dict[str, object]]
    prompt_version: str | None
    model_name: str | None
    reasoning_effort: str | None
    token_usage_input: int | None
    token_usage_output: int | None
    cost_estimate: float | None
    failure_type: str | None
    started_at: datetime | None
    completed_at: datetime | None
    input_snapshot: dict[str, object] | None = None


@dataclass
class FunctionalAnalysisResult:
    status: str
    summary: str
    risk_points: list[str]
    factor_breakdown: list[dict[str, object]]
    generated_at: datetime
    used_web_search: bool
    web_search_status: str
    web_sources: list[dict[str, object]]
    prompt_version: str | None
    model_name: str | None
    reasoning_effort: str | None
    token_usage_input: int | None
    token_usage_output: int | None
    cost_estimate: float | None
    failure_type: str | None
    analysis_mode: str
    orchestrator_version: str
    selected_hypothesis: str | None
    decision_confidence: str | None
    decision_reason_summary: str | None
    pipeline_roles: list[FunctionalRoleResult]
    role_progress: list[dict[str, object]]
    active_role_key: str | None
    pipeline_stage: str


def normalize_analysis_mode(requested_mode: str | None, *, trigger_source: str) -> str:
    mode = str(requested_mode or ANALYSIS_MODE_SINGLE).strip().lower()
    if mode != ANALYSIS_MODE_FUNCTIONAL_MULTI_AGENT:
        return ANALYSIS_MODE_SINGLE
    return mode if trigger_source == "manual" else ANALYSIS_MODE_SINGLE


def to_json_safe_payload(value: object) -> object:
    # 关键流程：多 Agent 输出会进入数据库 JSON 列，这里统一做递归安全化，
    # 避免 date/datetime/Decimal 等 Python 对象在 finalizing 阶段卡死事务。
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, Enum):
        return to_json_safe_payload(value.value)
    if isinstance(value, dict):
        return {
            str(key): to_json_safe_payload(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [to_json_safe_payload(item) for item in value]
    if is_dataclass(value):
        return to_json_safe_payload(asdict(value))
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return to_json_safe_payload(model_dump(mode="json"))
    return str(value)


def build_functional_prompt_version(role_key: str, *, max_length: int = 32) -> str:
    normalized_role_key = re.sub(r"[^a-z0-9_]+", "_", str(role_key).strip().lower())
    prefix = f"{FUNCTIONAL_PROMPT_VERSION_PREFIX}:"
    available_length = max(1, max_length - len(prefix))
    return f"{prefix}{normalized_role_key[:available_length]}"


def _try_parse_json(text: str) -> dict[str, object] | None:
    candidates = [text.strip()]
    fenced = re.search(r"```json\s*(\{[\s\S]*\})\s*```", text, re.IGNORECASE)
    if fenced:
        candidates.insert(0, fenced.group(1))
    bare = re.search(r"(\{[\s\S]*\})", text)
    if bare:
        candidates.append(bare.group(1))
    for item in candidates:
        try:
            loaded = json.loads(item)
        except json.JSONDecodeError:
            continue
        if isinstance(loaded, dict):
            return loaded
    return None


def _fallback_plan(*, use_web_search: bool, events: list[dict[str, object]]) -> dict[str, object]:
    focus_buckets = ["stock_news", "announcements", "price_and_volume"]
    if any(str(item.get("event_type") or "").lower() == "policy" for item in events):
        focus_buckets.append("policy_documents")
    return {
        "summary": "已生成默认研究计划，优先检查新闻、公告、价格反馈与政策脉络。",
        "focus_buckets": focus_buckets,
        "priority_questions": [
            "是否已有价格或公告验证当前事件",
            "政策逻辑能否传导到公司层面",
            "是否存在明显反向证据",
        ],
        "web_search_recommended": bool(use_web_search),
        "evidence_targets": [{"bucket": bucket, "limit": 6} for bucket in focus_buckets],
    }


def _score_events(events: list[dict[str, object]]) -> tuple[int, int, int]:
    pos = neg = policy = 0
    for item in events:
        if str(item.get("sentiment_label") or "").lower() == "positive":
            pos += 1
        if str(item.get("sentiment_label") or "").lower() == "negative":
            neg += 1
        if str(item.get("event_type") or "").lower() == "policy":
            policy += 1
    return pos, neg, policy


def _fallback_hypotheses(*, name: str, ts_code: str, events: list[dict[str, object]], factor_weights: list[FactorWeight], gap_count: int) -> dict[str, object]:
    pos, neg, policy = _score_events(events)
    top = factor_weights[0] if factor_weights else None
    bull = pos + policy + (2 if top and top.direction == "positive" else 0)
    bear = neg + (2 if top and top.direction == "negative" else 0)
    neutral = max(1, gap_count + 1)
    return {
        "summary": "已生成三条候选假设。",
        "hypotheses": [
            {"key": "bullish_hypothesis", "title": "偏多假设", "summary": f"{name}（{ts_code}）当前偏向正向演绎。", "support_points": [str(item.get("title") or "") for item in events[:2]], "counter_points": [str(item.get("title") or "") for item in events[-1:]], "confidence": "high" if bull >= bear + 2 else "medium", "base_score": bull},
            {"key": "neutral_hypothesis", "title": "中性假设", "summary": f"{name}（{ts_code}）当前更适合保持观察。", "support_points": ["证据仍存在缺口。"] if gap_count else [], "counter_points": [], "confidence": "medium", "base_score": neutral},
            {"key": "bearish_hypothesis", "title": "偏谨慎假设", "summary": f"{name}（{ts_code}）当前仍需防范兑现不足。", "support_points": [str(item.get("title") or "") for item in events if str(item.get("sentiment_label") or "").lower() == "negative"][:2], "counter_points": [str(item.get("title") or "") for item in events[:1]], "confidence": "high" if bear >= bull + 2 else "medium", "base_score": bear},
        ],
    }


def _fallback_challenges(*, hypotheses: list[dict[str, object]], gap_count: int, conflict_count: int) -> dict[str, object]:
    reduction = min(3, gap_count + conflict_count)
    return {
        "summary": "已完成候选假设的反向质询。",
        "challenges": [
            {
                "hypothesis_key": str(item.get("key") or ""),
                "summary": "已从缺口、冲突与验证不足角度完成质询。",
                "weakness_points": ["证据缺口较多，方向判断可能被后续公告修正。"] if gap_count else ["当前缺口可控，但仍需持续验证。"],
                "unresolved_questions": ["价格与成交量反馈是否继续验证该假设。", "是否存在尚未披露的公告或监管变量。"],
                "reduction_score": reduction,
                "remaining_score": max(0, int(item.get("base_score") or 0) - reduction),
            }
            for item in hypotheses
        ],
    }


def _pick_decision(*, hypotheses: list[dict[str, object]], challenges: list[dict[str, object]], gap_count: int, conflict_count: int) -> dict[str, object]:
    reductions = {str(item.get("hypothesis_key") or ""): int(item.get("reduction_score") or 0) for item in challenges if isinstance(item, dict)}
    picked: dict[str, object] | None = None
    score = -999
    for item in hypotheses:
        key = str(item.get("key") or "")
        adjusted = int(item.get("base_score") or 0) - reductions.get(key, 0)
        if adjusted > score:
            score = adjusted
            picked = item
    confidence = "high" if score >= 4 and gap_count == 0 and conflict_count == 0 else "medium" if score >= 2 else "low"
    return {
        "selected_hypothesis": str((picked or {}).get("key") or "neutral_hypothesis"),
        "decision_confidence": confidence,
        "decision_reason_summary": str((picked or {}).get("summary") or "当前更适合保持观察。"),
    }


def _fallback_markdown(*, name: str, ts_code: str, decision: dict[str, object], hypotheses: list[dict[str, object]], gaps: list[str], challenges: list[dict[str, object]]) -> str:
    key = str(decision.get("selected_hypothesis") or "neutral_hypothesis")
    confidence = str(decision.get("decision_confidence") or "medium")
    summary = str(decision.get("decision_reason_summary") or "当前更适合保持观察。")
    selected = next((item for item in hypotheses if str(item.get("key") or "") == key), {})
    unresolved: list[str] = []
    for item in challenges:
        if str(item.get("hypothesis_key") or "") == key:
            unresolved = [str(q) for q in (item.get("unresolved_questions") or []) if str(q).strip()]
            break
    support = [str(item) for item in (selected.get("support_points") or []) if str(item).strip()]
    risk_points = unresolved or gaps[:2] or ["需继续关注公告兑现与价格反馈。"]
    return "\n".join([
        "## 核心判断",
        f"{name}（{ts_code}）当前更适合按“{key}”理解，综合置信度为 {confidence}。{summary}",
        "",
        "## 关键证据",
        *([f"- {item}" for item in support] or ["- 当前主要依据来自结构化事件、价格反馈与证据审计结果。"]),
        "",
        "## 风险提示",
        *[f"- {item}" for item in risk_points],
    ]).strip()


async def _emit(cb: ROLE_EVENT | None, event_name: str, payload: dict[str, object]) -> None:
    if cb is not None:
        await cb(event_name, payload)


async def _run_json_role(*, role_key: str, role_label: str, sort_order: int, system_instruction: str, prompt: str, fallback: dict[str, object], use_web_search: bool, input_snapshot: dict[str, object] | None) -> FunctionalRoleResult:
    started = datetime.now(UTC)
    failure_type = None
    try:
        llm = await generate_llm_result(prompt, system_instruction=system_instruction, max_output_tokens=800, use_web_search=use_web_search)
        payload = to_json_safe_payload(_try_parse_json(llm.text) or fallback)
        status = "completed"
    except Exception as exc:
        llm = LlmTextResult(text="", used_web_search=False, web_search_status="unsupported" if use_web_search else "disabled", web_sources=[], model_name="", reasoning_effort="", token_usage_input=None, token_usage_output=None)
        payload = to_json_safe_payload(fallback)
        status = "partial"
        failure_type = type(exc).__name__
    summary = str(payload.get("summary") or f"{role_label} 已完成。")
    normalized_input_snapshot = to_json_safe_payload(input_snapshot)
    return FunctionalRoleResult(
        role_key,
        role_label,
        status,
        sort_order,
        summary,
        payload,
        llm.used_web_search,
        llm.web_search_status,
        llm.web_sources,
        build_functional_prompt_version(role_key),
        llm.model_name or None,
        llm.reasoning_effort or None,
        llm.token_usage_input,
        llm.token_usage_output,
        None,
        failure_type,
        started,
        datetime.now(UTC),
        normalized_input_snapshot if isinstance(normalized_input_snapshot, dict) else None,
    )


async def run_functional_multi_agent_analysis(*, session: AsyncSession, session_row, instrument, latest_snapshot, event_payloads: list[dict[str, object]], factor_weights: list[FactorWeight], on_final_delta: TEXT_EVENT | None = None, on_role_event: ROLE_EVENT | None = None) -> FunctionalAnalysisResult:
    _ = session
    name = getattr(instrument, "name", None) or session_row.ts_code
    roles: list[FunctionalRoleResult] = []
    await _emit(on_role_event, "role_status", {"role_key": "research_planner", "role_label": "研究规划", "status": "running"})
    planner = await _run_json_role(role_key="research_planner", role_label="研究规划", sort_order=1, system_instruction="你是研究规划 Agent，只能输出 JSON，不允许给投资建议。", prompt=f"请围绕 {session_row.ts_code} 生成研究计划 JSON，字段至少包含 summary、focus_buckets、priority_questions、web_search_recommended、evidence_targets。", fallback=_fallback_plan(use_web_search=bool(session_row.use_web_search), events=event_payloads), use_web_search=False, input_snapshot={"ts_code": session_row.ts_code, "event_count": len(event_payloads)})
    roles.append(planner)
    await _emit(on_role_event, "role_completed", {"role_key": planner.role_key, "role_label": planner.role_label, "status": planner.status})

    ledger = []
    bucket_counts: dict[str, int] = {}
    for item in event_payloads:
        event_type = str(item.get("event_type") or "").lower()
        bucket = "policy_documents" if event_type == "policy" else "announcements" if event_type == "announcement" else "stock_news"
        row = {"evidence_id": str(item.get("event_id") or ""), "bucket": bucket, "scope": str(item.get("scope") or ""), "title": str(item.get("title") or ""), "summary": str(item.get("title") or ""), "published_at": item.get("published_at"), "source": str(item.get("source") or ""), "provider": str(item.get("source") or ""), "url": item.get("url"), "ts_code": session_row.ts_code, "topic": session_row.topic, "event_type": item.get("event_type"), "source_priority": item.get("source_priority"), "is_structured": True, "is_web_search": False}
        ledger.append(row)
        bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1
    if latest_snapshot is not None:
        ledger.append({"evidence_id": f"snapshot:{session_row.ts_code}", "bucket": "price_and_volume", "scope": "snapshot", "title": f"{session_row.ts_code} 最新行情快照", "summary": f"收盘价 {getattr(latest_snapshot, 'close', None)}，涨跌幅 {getattr(latest_snapshot, 'pct_chg', None)}", "published_at": to_json_safe_payload(getattr(latest_snapshot, "trade_date", None)), "source": "stock_daily_snapshots", "provider": "tushare", "url": None, "ts_code": session_row.ts_code, "topic": session_row.topic, "event_type": "snapshot", "source_priority": 100, "is_structured": True, "is_web_search": False})
        bucket_counts["price_and_volume"] = bucket_counts.get("price_and_volume", 0) + 1
    retrieval = FunctionalRoleResult("evidence_retrieval", "证据检索", "completed", 2, "已整理原始证据账本。", to_json_safe_payload({"summary": "已根据研究计划整理证据账本。", "bucket_counts": bucket_counts, "total_items": len(ledger), "items": ledger[:8]}), False, "disabled", [], build_functional_prompt_version("evidence_retrieval"), None, None, None, None, None, None, datetime.now(UTC), datetime.now(UTC), to_json_safe_payload({"focus_buckets": planner.output_payload.get("focus_buckets", [])}))
    roles.append(retrieval)
    await _emit(on_role_event, "role_completed", {"role_key": retrieval.role_key, "role_label": retrieval.role_label, "status": retrieval.status})

    seen: set[str] = set()
    duplicate = 0
    gaps: list[str] = []
    for item in ledger:
        title = str(item.get("title") or "").strip()
        if title and title in seen:
            duplicate += 1
        seen.add(title)
        if not item.get("published_at"):
            gaps.append(f"{title or '部分证据'} 缺少明确发布时间。")
    pos, neg, _policy = _score_events(event_payloads)
    conflict = 1 if pos and neg else 0
    if conflict:
        gaps.append("正负向事件同时存在，需警惕结论过于单边。")
    audit_payload = to_json_safe_payload({"summary": "已完成证据审计。", "overall_quality": "high" if not gaps and duplicate == 0 else "medium" if len(gaps) <= 2 else "low", "duplicate_title_count": duplicate, "conflict_count": conflict, "gap_count": len(gaps), "gaps": gaps[:5], "scorecard": {"structured_event_count": len(event_payloads), "bucket_count": len(bucket_counts), "has_price_snapshot": latest_snapshot is not None}})
    audit = FunctionalRoleResult("evidence_audit", "证据审计", "completed", 3, "已完成证据审计。", audit_payload, False, "disabled", [], build_functional_prompt_version("evidence_audit"), None, None, None, None, None, None, datetime.now(UTC), datetime.now(UTC), to_json_safe_payload({"raw_item_count": len(ledger)}))
    roles.append(audit)
    await _emit(on_role_event, "role_completed", {"role_key": audit.role_key, "role_label": audit.role_label, "status": audit.status})

    await _emit(on_role_event, "role_status", {"role_key": "hypothesis_builder", "role_label": "候选假设", "status": "running"})
    hypotheses = await _run_json_role(role_key="hypothesis_builder", role_label="候选假设", sort_order=4, system_instruction="你是候选假设 Agent，只能输出 JSON，必须同时给出 bullish_hypothesis、neutral_hypothesis、bearish_hypothesis。", prompt=f"请围绕 {session_row.ts_code} 输出三种候选假设 JSON，字段至少包含 summary 和 hypotheses。每个 hypothesis 至少包含 key、title、summary、support_points、counter_points、confidence、base_score。", fallback=_fallback_hypotheses(name=name, ts_code=session_row.ts_code, events=event_payloads, factor_weights=factor_weights, gap_count=int(audit_payload['gap_count'])), use_web_search=bool(session_row.use_web_search), input_snapshot={"event_count": len(event_payloads), "factor_count": len(factor_weights), "audit_quality": audit_payload["overall_quality"]})
    roles.append(hypotheses)
    await _emit(on_role_event, "role_completed", {"role_key": hypotheses.role_key, "role_label": hypotheses.role_label, "status": hypotheses.status})

    hypothesis_items = [item for item in (hypotheses.output_payload.get("hypotheses") or []) if isinstance(item, dict)]
    challenge_payload = _fallback_challenges(hypotheses=hypothesis_items, gap_count=int(audit_payload["gap_count"]), conflict_count=int(audit_payload["conflict_count"]))
    challenge = FunctionalRoleResult("challenge_agent", "反向质询", "completed", 5, "已完成候选假设的反向质询。", challenge_payload, False, "disabled", [], build_functional_prompt_version("challenge_agent"), None, None, None, None, None, None, datetime.now(UTC), datetime.now(UTC), {"hypothesis_count": len(hypothesis_items)})
    roles.append(challenge)
    await _emit(on_role_event, "role_completed", {"role_key": challenge.role_key, "role_label": challenge.role_label, "status": challenge.status})

    decision = _pick_decision(hypotheses=hypothesis_items, challenges=[item for item in (challenge.output_payload.get("challenges") or []) if isinstance(item, dict)], gap_count=int(audit_payload["gap_count"]), conflict_count=int(audit_payload["conflict_count"]))
    await _emit(on_role_event, "role_status", {"role_key": "decision_agent", "role_label": "最终裁决", "status": "running"})
    decision_text = ""
    decision_failure_type = None
    decision_llm: LlmTextResult | None = None

    async def _handle_delta(delta: str) -> None:
        nonlocal decision_text
        decision_text += delta
        if on_final_delta is not None:
            await on_final_delta(delta)
        await _emit(on_role_event, "role_delta", {"role_key": "decision_agent", "role_label": "最终裁决", "delta": delta, "content": decision_text})

    try:
        decision_llm = await generate_streamed_llm_result(
            f"请基于以下信息生成 {session_row.ts_code} 的中文 Markdown 股票分析简报。最终采纳假设：{decision['selected_hypothesis']}。最终置信度：{decision['decision_confidence']}。采纳理由：{decision['decision_reason_summary']}。仅使用二级标题：## 核心判断、## 关键证据、## 风险提示。不要输出过程说明。",
            system_instruction="你是最终裁决 Agent，负责把研究流水线的结论整理为用户可读的中文 Markdown 报告。只输出 Markdown。",
            max_output_tokens=900,
            use_web_search=False,
            on_delta=_handle_delta,
        )
        if not decision_text.strip():
            decision_text = decision_llm.text.strip()
    except Exception as exc:
        decision_failure_type = type(exc).__name__
        decision_text = _fallback_markdown(name=name, ts_code=session_row.ts_code, decision=decision, hypotheses=hypothesis_items, gaps=[str(item) for item in audit_payload["gaps"]], challenges=[item for item in (challenge.output_payload.get("challenges") or []) if isinstance(item, dict)])
        if on_final_delta is not None:
            await on_final_delta(decision_text)

    decision_role = FunctionalRoleResult("decision_agent", "最终裁决", "completed" if decision_failure_type is None else "partial", 6, str(decision.get("decision_reason_summary") or ""), to_json_safe_payload({"selected_hypothesis": decision["selected_hypothesis"], "decision_confidence": decision["decision_confidence"], "decision_reason_summary": decision["decision_reason_summary"]}), decision_llm.used_web_search if decision_llm else False, decision_llm.web_search_status if decision_llm else "disabled", decision_llm.web_sources if decision_llm else [], build_functional_prompt_version("decision_agent"), decision_llm.model_name if decision_llm and decision_llm.model_name else None, decision_llm.reasoning_effort if decision_llm and decision_llm.reasoning_effort else None, decision_llm.token_usage_input if decision_llm else None, decision_llm.token_usage_output if decision_llm else None, None, decision_failure_type, datetime.now(UTC), datetime.now(UTC), to_json_safe_payload({"selected_hypothesis": decision["selected_hypothesis"]}))
    roles.append(decision_role)
    await _emit(on_role_event, "role_completed", {"role_key": decision_role.role_key, "role_label": decision_role.role_label, "status": decision_role.status})

    all_sources: list[dict[str, object]] = []
    for role in roles:
        for item in role.web_sources:
            if item not in all_sources:
                all_sources.append(item)
    risks = [str(item) for item in audit_payload["gaps"]]
    for item in challenge.output_payload.get("challenges") or []:
        if isinstance(item, dict) and str(item.get("hypothesis_key") or "") == str(decision["selected_hypothesis"]):
            risks.extend(str(q) for q in (item.get("unresolved_questions") or []) if str(q).strip())
            break
    deduped: list[str] = []
    seen_risks: set[str] = set()
    for item in risks or ["需继续关注公告兑现与价格反馈。"]:
        if item in seen_risks:
            continue
        seen_risks.add(item)
        deduped.append(item)
    return FunctionalAnalysisResult(
        status="ready" if all(item.status == "completed" for item in roles) else "partial",
        summary=decision_text,
        risk_points=deduped[:5],
        factor_breakdown=[{"factor_key": item.factor_key, "factor_label": item.factor_label, "weight": item.weight, "direction": item.direction, "evidence": item.evidence, "reason": item.reason} for item in factor_weights],
        generated_at=datetime.now(UTC),
        used_web_search=any(item.used_web_search for item in roles),
        web_search_status="used" if any(item.used_web_search for item in roles) else "disabled",
        web_sources=all_sources,
        prompt_version=decision_role.prompt_version,
        model_name=decision_role.model_name,
        reasoning_effort=decision_role.reasoning_effort,
        token_usage_input=sum(value for value in [item.token_usage_input for item in roles] if isinstance(value, int)) or None,
        token_usage_output=sum(value for value in [item.token_usage_output for item in roles] if isinstance(value, int)) or None,
        cost_estimate=None,
        failure_type=decision_failure_type,
        analysis_mode=ANALYSIS_MODE_FUNCTIONAL_MULTI_AGENT,
        orchestrator_version=FUNCTIONAL_MULTI_AGENT_ORCHESTRATOR_VERSION,
        selected_hypothesis=str(decision["selected_hypothesis"]),
        decision_confidence=str(decision["decision_confidence"]),
        decision_reason_summary=str(decision["decision_reason_summary"]),
        pipeline_roles=roles,
        role_progress=[{"role_key": item.role_key, "role_label": item.role_label, "status": item.status, "sort_order": item.sort_order} for item in roles],
        active_role_key="decision_agent",
        pipeline_stage="decisioning",
    )
