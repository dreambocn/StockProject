from dataclasses import dataclass
from datetime import datetime, UTC
from typing import Awaitable, Callable, Iterable

from app.services.analysis_prompt_service import build_analysis_prompt
from app.services.factor_weight_service import FactorWeight
from app.services.llm_client_service import generate_llm_result, stream_llm_text


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


async def generate_stock_analysis_report(
    ts_code: str,
    instrument_name: str | None,
    events: Iterable[dict[str, object]],
    factor_weights: Iterable[FactorWeight],
    *,
    client: object | None = None,
    use_web_search: bool = False,
    on_delta: Callable[[str], Awaitable[None]] | None = None,
) -> AnalysisReportResult:
    prompt = build_analysis_prompt(
        ts_code=ts_code,
        instrument_name=instrument_name,
        events=events,
        factor_weights=factor_weights,
    )
    try:
        if on_delta is not None:
            chunks: list[str] = []
            async for delta in stream_llm_text(
                prompt,
                client=client,
                max_output_tokens=512,
                use_web_search=use_web_search,
            ):
                chunks.append(delta)
                await on_delta(delta)
            summary = "".join(chunks).strip()
            used_web_search = use_web_search
            web_search_status = "used" if use_web_search else "disabled"
            web_sources: list[dict[str, object]] = []
        else:
            llm_result = await generate_llm_result(
                prompt,
                client=client,
                max_output_tokens=512,
                use_web_search=use_web_search,
            )
            summary = llm_result.text
            used_web_search = llm_result.used_web_search
            web_search_status = llm_result.web_search_status
            web_sources = llm_result.web_sources

        if not summary:
            raise RuntimeError("empty llm summary")
        status = "ready"
    except Exception:
        summary = (
            "由于大模型暂不可用，当前仅返回基于规则的摘要，后续会补齐分析。"
        )
        status = "partial"
        used_web_search = False
        web_search_status = "unsupported" if use_web_search else "disabled"
        web_sources = []

    factor_breakdown = [
        {
            "factor_key": factor.factor_key,
            "factor_label": factor.factor_label,
            "weight": factor.weight,
            "direction": factor.direction,
            "evidence": factor.evidence,
            "reason": factor.reason,
        }
        for factor in factor_weights
    ]

    risk_points = [f"事件：{event.get('title', '未知')} 可能带来的风险" for event in events]

    return AnalysisReportResult(
        status=status,
        summary=summary,
        risk_points=risk_points,
        factor_breakdown=factor_breakdown,
        generated_at=datetime.now(UTC),
        used_web_search=used_web_search,
        web_search_status=web_search_status,
        web_sources=web_sources,
    )
