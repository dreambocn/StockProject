import inspect
from dataclasses import dataclass
from datetime import datetime, UTC
import re
from typing import Awaitable, Callable, Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.analysis_prompt_service import (
    build_analysis_prompt,
    build_analysis_system_instruction,
)
from app.services.analysis_prompt_registry import get_analysis_prompt_version
from app.services.factor_weight_service import FactorWeight
from app.services.llm_client_service import generate_llm_result, generate_streamed_llm_result
from app.services.web_source_metadata_service import enrich_web_sources


@dataclass
class AnalysisReportResult:
    status: str
    summary: str
    risk_points: list[str]
    factor_breakdown: list[dict[str, object]]
    generated_at: datetime
    used_web_search: bool
    web_search_status: str
    web_sources: list[dict[str, object]]
    prompt_version: str = ""
    model_name: str = ""
    reasoning_effort: str = ""
    token_usage_input: int | None = None
    token_usage_output: int | None = None
    cost_estimate: float | None = None
    failure_type: str | None = None


AGENTIC_OUTPUT_PATTERNS = (
    "准备先查看",
    "查看仓库",
    "仓库根目录",
    "文件结构",
    "现有文档",
    "工具调用",
    "我将先",
    "我会先",
    "当前分析状态 ·",
    "先看结论，再回溯证据与风险。",
)


def _contains_agentic_output(summary: str) -> bool:
    normalized_summary = summary.strip()
    if not normalized_summary:
        return False

    # 过滤“代理自述”类文本，避免污染终端用户可见的分析结论。
    return any(pattern in normalized_summary for pattern in AGENTIC_OUTPUT_PATTERNS)


def _sanitize_analysis_summary(summary: str) -> str:
    sanitized_lines: list[str] = []
    for raw_line in summary.splitlines():
        line = raw_line.strip()
        if not line:
            sanitized_lines.append("")
            continue
        # 如果检测到代理流程输出，直接丢弃整行。
        if any(pattern in line for pattern in AGENTIC_OUTPUT_PATTERNS):
            continue
        sanitized_lines.append(raw_line.rstrip())

    sanitized = "\n".join(sanitized_lines).strip()
    sanitized = re.sub(r"\n{3,}", "\n\n", sanitized).strip()
    if _contains_agentic_output(sanitized):
        return ""
    return sanitized


def _build_rule_based_summary(
    *,
    ts_code: str,
    instrument_name: str | None,
    events: Iterable[dict[str, object]],
    factor_weights: Iterable[FactorWeight],
) -> str:
    resolved_name = instrument_name or ts_code
    factor_list = list(factor_weights)
    event_list = list(events)
    top_factor = factor_list[0] if factor_list else None
    direction_label_map = {
        "positive": "利好",
        "negative": "利空",
        "neutral": "中性",
    }

    conclusion = (
        f"{resolved_name}（{ts_code}）当前可结合事件驱动做跟踪，"
        f"但建议优先核对最新公告与交易反馈。"
    )
    if top_factor is not None:
        direction_label = direction_label_map.get(
            top_factor.direction,
            top_factor.direction,
        )
        conclusion = (
            f"{resolved_name}（{ts_code}）当前主要受“{top_factor.factor_label}”驱动，"
            f"方向偏{direction_label}，但仍需结合事件证据二次确认。"
        )

    evidence_lines = [
        f"- {event.get('title') or '暂无明确事件'}"
        for event in event_list[:3]
    ] or ["- 暂无可用事件证据"]
    risk_lines = [
        f"- 需持续确认：{event.get('title') or '暂无明确事件'}"
        for event in event_list[:2]
    ] or ["- 当前事件证据不足，建议继续观察。"]

    return "\n".join(
        [
            "## 核心判断",
            conclusion,
            "",
            "## 关键证据",
            *evidence_lines,
            "",
            "## 风险提示",
            *risk_lines,
        ]
    ).strip()


def _supports_keyword_argument(func: object, keyword: str) -> bool:
    try:
        signature = inspect.signature(func)
    except (TypeError, ValueError):
        return False

    parameter = signature.parameters.get(keyword)
    if parameter is None:
        return False
    return parameter.kind in {
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
        inspect.Parameter.KEYWORD_ONLY,
    }


def _read_llm_result_attr(result: object, name: str, default):
    value = getattr(result, name, default)
    return default if value is None else value


async def generate_stock_analysis_report(
    ts_code: str,
    instrument_name: str | None,
    events: Iterable[dict[str, object]],
    factor_weights: Iterable[FactorWeight],
    *,
    session: AsyncSession | None = None,
    client: object | None = None,
    use_web_search: bool = False,
    on_delta: Callable[[str], Awaitable[None]] | None = None,
) -> AnalysisReportResult:
    factor_weight_list = list(factor_weights)
    event_list = list(events)
    prompt_version = get_analysis_prompt_version()
    prompt = build_analysis_prompt(
        ts_code=ts_code,
        instrument_name=instrument_name,
        events=event_list,
        factor_weights=factor_weight_list,
    )
    system_instruction = build_analysis_system_instruction()
    used_web_search = False
    web_search_status = "disabled"
    web_sources: list[dict[str, object]] = []
    model_name = ""
    reasoning_level = ""
    token_usage_input: int | None = None
    token_usage_output: int | None = None
    failure_type: str | None = None
    try:
        # 有 on_delta 时走流式输出，用于前端实时展示进度与摘要片段。
        if on_delta is not None:
            stream_kwargs: dict[str, object] = {
                "client": client,
                "system_instruction": system_instruction,
                "max_output_tokens": 512,
                "use_web_search": use_web_search,
            }
            # 兼容旧测试桩与旧实现：只有目标函数显式支持 on_delta 时才透传。
            if _supports_keyword_argument(generate_streamed_llm_result, "on_delta"):
                stream_kwargs["on_delta"] = on_delta
            llm_result = await generate_streamed_llm_result(
                prompt,
                **stream_kwargs,
            )
            used_web_search = bool(
                _read_llm_result_attr(llm_result, "used_web_search", False)
            )
            web_search_status = str(
                _read_llm_result_attr(llm_result, "web_search_status", "disabled")
            )
            web_sources = list(_read_llm_result_attr(llm_result, "web_sources", []))
            model_name = str(_read_llm_result_attr(llm_result, "model_name", ""))
            reasoning_level = str(
                _read_llm_result_attr(llm_result, "reasoning_effort", "")
            )
            token_usage_input = _read_llm_result_attr(
                llm_result,
                "token_usage_input",
                None,
            )
            token_usage_output = _read_llm_result_attr(
                llm_result,
                "token_usage_output",
                None,
            )
            summary = _sanitize_analysis_summary(llm_result.text)
            if not summary:
                raise RuntimeError("dirty llm summary")
            await on_delta(summary)
        else:
            llm_result = await generate_llm_result(
                prompt,
                client=client,
                system_instruction=system_instruction,
                max_output_tokens=512,
                use_web_search=use_web_search,
            )
            used_web_search = bool(
                _read_llm_result_attr(llm_result, "used_web_search", False)
            )
            web_search_status = str(
                _read_llm_result_attr(llm_result, "web_search_status", "disabled")
            )
            web_sources = list(_read_llm_result_attr(llm_result, "web_sources", []))
            model_name = str(_read_llm_result_attr(llm_result, "model_name", ""))
            reasoning_level = str(
                _read_llm_result_attr(llm_result, "reasoning_effort", "")
            )
            token_usage_input = _read_llm_result_attr(
                llm_result,
                "token_usage_input",
                None,
            )
            token_usage_output = _read_llm_result_attr(
                llm_result,
                "token_usage_output",
                None,
            )
            summary = _sanitize_analysis_summary(llm_result.text)
            if not summary:
                raise RuntimeError("dirty llm summary")

        if not summary:
            raise RuntimeError("empty llm summary")
        status = "ready"
    except Exception as exc:
        # 关键降级：LLM 失败时回退规则化摘要，保证分析页面始终有可展示内容。
        summary = _build_rule_based_summary(
            ts_code=ts_code,
            instrument_name=instrument_name,
            events=event_list,
            factor_weights=factor_weight_list,
        )
        status = "partial"
        failure_type = type(exc).__name__
        if use_web_search and web_search_status == "disabled":
            # 当环境不支持 web_search 时标记为 unsupported，避免前端误判为成功检索。
            web_search_status = "unsupported"
            used_web_search = False

    if web_sources and session is not None:
        # 仅在有来源且持有数据库会话时补全元数据，避免纯计算场景阻塞。
        web_sources = await enrich_web_sources(
            session=session,
            raw_sources=web_sources,
        )

    factor_breakdown = [
        {
            "factor_key": factor.factor_key,
            "factor_label": factor.factor_label,
            "weight": factor.weight,
            "direction": factor.direction,
            "evidence": factor.evidence,
            "reason": factor.reason,
        }
        for factor in factor_weight_list
    ]

    risk_points = [
        f"事件：{event.get('title', '未知')} 可能带来的风险"
        for event in event_list
    ]

    return AnalysisReportResult(
        status=status,
        summary=summary,
        risk_points=risk_points,
        factor_breakdown=factor_breakdown,
        generated_at=datetime.now(UTC),
        used_web_search=used_web_search,
        web_search_status=web_search_status,
        web_sources=web_sources,
        prompt_version=prompt_version,
        model_name=model_name,
        reasoning_effort=reasoning_level,
        token_usage_input=token_usage_input,
        token_usage_output=token_usage_output,
        cost_estimate=None,
        failure_type=failure_type,
    )
