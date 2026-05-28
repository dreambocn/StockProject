import asyncio
import json
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace

from app.services.analysis_orchestrator_service import (
    build_functional_prompt_version,
    run_functional_multi_agent_analysis,
    to_json_safe_payload,
)
from app.services.llm_client_service import LlmTextResult


def test_to_json_safe_payload_normalizes_non_json_native_values() -> None:
    payload = {
        "trade_date": date(2026, 4, 10),
        "generated_at": datetime(2026, 4, 10, 9, 30, tzinfo=UTC),
        "price": Decimal("1500.25"),
        "windows": ("T+1", "T+5"),
        "tags": {"policy", "stock"},
        "nested": {
            "updated_at": datetime(2026, 4, 10, 9, 35, tzinfo=UTC),
        },
    }

    normalized = to_json_safe_payload(payload)

    # 关键断言：多 Agent 角色输出必须先转成 JSON 安全结构，才能进入数据库 JSON 列。
    assert normalized["trade_date"] == "2026-04-10"
    assert normalized["generated_at"] == "2026-04-10T09:30:00+00:00"
    assert normalized["price"] == 1500.25
    assert normalized["windows"] == ["T+1", "T+5"]
    assert sorted(normalized["tags"]) == ["policy", "stock"]
    assert normalized["nested"]["updated_at"] == "2026-04-10T09:35:00+00:00"

    json.dumps(normalized)


def test_build_functional_prompt_version_stays_within_prompt_column_limit() -> None:
    prompt_version = build_functional_prompt_version("decision_agent")

    # 报告与角色运行记录的 prompt_version 列当前是 VARCHAR(32)，这里要确保不会再写爆。
    assert prompt_version == "fma-v1:decision_agent"
    assert len(prompt_version) <= 32


def test_functional_multi_agent_enables_web_search_for_each_role(
    monkeypatch,
) -> None:
    json_role_calls: list[bool] = []
    streamed_role_calls: list[bool] = []

    async def fake_generate_llm_result(
        prompt: str,
        *,
        system_instruction: str | None = None,
        max_output_tokens: int = 800,
        use_web_search: bool = False,
    ) -> LlmTextResult:
        _ = prompt, system_instruction, max_output_tokens
        json_role_calls.append(use_web_search)
        return LlmTextResult(
            text=json.dumps({"summary": "角色已完成联网增强。"}),
            used_web_search=use_web_search,
            web_search_status="used" if use_web_search else "disabled",
            web_sources=[],
            model_name="test-model",
            reasoning_effort="medium",
            token_usage_input=5,
            token_usage_output=6,
        )

    async def fake_generate_streamed_llm_result(
        prompt: str,
        *,
        system_instruction: str | None = None,
        max_output_tokens: int = 900,
        use_web_search: bool = False,
        on_delta=None,
    ) -> LlmTextResult:
        _ = prompt, system_instruction, max_output_tokens
        streamed_role_calls.append(use_web_search)
        if on_delta is not None:
            await on_delta("## 核心判断\n联网增强已覆盖最终裁决。")
        return LlmTextResult(
            text="## 核心判断\n联网增强已覆盖最终裁决。",
            used_web_search=use_web_search,
            web_search_status="used" if use_web_search else "disabled",
            web_sources=[],
            model_name="test-model",
            reasoning_effort="medium",
            token_usage_input=8,
            token_usage_output=9,
        )

    monkeypatch.setattr(
        "app.services.analysis_orchestrator_service.generate_llm_result",
        fake_generate_llm_result,
    )
    monkeypatch.setattr(
        "app.services.analysis_orchestrator_service.generate_streamed_llm_result",
        fake_generate_streamed_llm_result,
    )

    async def run_test() -> None:
        result = await run_functional_multi_agent_analysis(
            session=SimpleNamespace(),
            session_row=SimpleNamespace(
                ts_code="600519.SH",
                topic="watchlist",
                use_web_search=True,
            ),
            instrument=SimpleNamespace(name="贵州茅台"),
            latest_snapshot=None,
            event_payloads=[
                {
                    "event_id": "event-1",
                    "event_type": "news",
                    "scope": "stock",
                    "title": "公司发布经营进展",
                    "published_at": "2026-05-29T09:00:00+00:00",
                    "source": "测试源",
                    "url": "https://example.com/event-1",
                }
            ],
            factor_weights=[],
        )

        assert len(result.pipeline_roles) == 6
        assert json_role_calls == [True, True, True, True, True]
        assert streamed_role_calls == [True]
        assert all(role.web_search_status == "used" for role in result.pipeline_roles)
        assert result.web_search_status == "used"

    asyncio.run(run_test())


def test_functional_multi_agent_keeps_ready_when_web_search_falls_back(
    monkeypatch,
) -> None:
    async def fake_generate_llm_result(
        prompt: str,
        *,
        system_instruction: str | None = None,
        max_output_tokens: int = 800,
        use_web_search: bool = False,
    ) -> LlmTextResult:
        _ = prompt, system_instruction, max_output_tokens
        if use_web_search:
            return LlmTextResult(
                text=json.dumps(
                    {
                        "summary": "联网工具不支持，已使用普通模型生成候选假设。",
                        "hypotheses": [
                            {
                                "key": "neutral_hypothesis",
                                "title": "中性观察",
                                "summary": "事件影响仍需观察。",
                                "support_points": ["结构化事件仍可使用。"],
                                "counter_points": ["外部检索不可用。"],
                                "confidence": "medium",
                                "base_score": 0.52,
                            }
                        ],
                    }
                ),
                used_web_search=False,
                web_search_status="unsupported",
                web_sources=[],
                model_name="test-model",
                reasoning_effort="medium",
                token_usage_input=10,
                token_usage_output=20,
            )
        return LlmTextResult(
            text=json.dumps(
                {
                    "summary": "已生成研究计划。",
                    "focus_buckets": ["stock_news"],
                    "priority_questions": ["事件是否影响订单？"],
                    "web_search_recommended": True,
                    "evidence_targets": ["公告"],
                }
            ),
            used_web_search=False,
            web_search_status="disabled",
            web_sources=[],
            model_name="test-model",
            reasoning_effort="medium",
            token_usage_input=5,
            token_usage_output=6,
        )

    async def fake_generate_streamed_llm_result(
        prompt: str,
        *,
        system_instruction: str | None = None,
        max_output_tokens: int = 900,
        use_web_search: bool = False,
        on_delta=None,
    ) -> LlmTextResult:
        _ = prompt, system_instruction, max_output_tokens, use_web_search
        if on_delta is not None:
            await on_delta("## 核心判断\n普通模型回退后仍完成分析。")
        return LlmTextResult(
            text="## 核心判断\n普通模型回退后仍完成分析。",
            used_web_search=False,
            web_search_status="disabled",
            web_sources=[],
            model_name="test-model",
            reasoning_effort="medium",
            token_usage_input=8,
            token_usage_output=9,
        )

    monkeypatch.setattr(
        "app.services.analysis_orchestrator_service.generate_llm_result",
        fake_generate_llm_result,
    )
    monkeypatch.setattr(
        "app.services.analysis_orchestrator_service.generate_streamed_llm_result",
        fake_generate_streamed_llm_result,
    )

    async def run_test() -> None:
        result = await run_functional_multi_agent_analysis(
            session=SimpleNamespace(),
            session_row=SimpleNamespace(
                ts_code="600519.SH",
                topic="watchlist",
                use_web_search=True,
            ),
            instrument=SimpleNamespace(name="贵州茅台"),
            latest_snapshot=None,
            event_payloads=[
                {
                    "event_id": "event-1",
                    "event_type": "news",
                    "scope": "stock",
                    "title": "公司发布经营进展",
                    "published_at": "2026-05-29T09:00:00+00:00",
                    "source": "测试源",
                    "url": "https://example.com/event-1",
                }
            ],
            factor_weights=[],
        )

        hypothesis_role = next(
            role for role in result.pipeline_roles if role.role_key == "hypothesis_builder"
        )
        assert result.status == "ready"
        assert result.web_search_status == "unsupported"
        assert result.used_web_search is False
        assert hypothesis_role.status == "completed"
        assert hypothesis_role.web_search_status == "unsupported"

    asyncio.run(run_test())


def test_functional_multi_agent_marks_partial_when_role_fallback_is_used(
    monkeypatch,
) -> None:
    async def fake_generate_llm_result(
        prompt: str,
        *,
        system_instruction: str | None = None,
        max_output_tokens: int = 800,
        use_web_search: bool = False,
    ) -> LlmTextResult:
        _ = prompt, system_instruction, max_output_tokens
        if use_web_search:
            raise RuntimeError("web_search tool unsupported and fallback failed")
        return LlmTextResult(
            text=json.dumps(
                {
                    "summary": "已生成研究计划。",
                    "focus_buckets": ["stock_news"],
                    "priority_questions": ["事件是否影响订单？"],
                    "web_search_recommended": True,
                    "evidence_targets": ["公告"],
                }
            ),
            used_web_search=False,
            web_search_status="disabled",
            web_sources=[],
            model_name="test-model",
            reasoning_effort="medium",
            token_usage_input=5,
            token_usage_output=6,
        )

    async def fake_generate_streamed_llm_result(
        prompt: str,
        *,
        system_instruction: str | None = None,
        max_output_tokens: int = 900,
        use_web_search: bool = False,
        on_delta=None,
    ) -> LlmTextResult:
        _ = prompt, system_instruction, max_output_tokens, use_web_search
        if on_delta is not None:
            await on_delta("## 核心判断\n规则 fallback 后生成分析。")
        return LlmTextResult(
            text="## 核心判断\n规则 fallback 后生成分析。",
            used_web_search=False,
            web_search_status="disabled",
            web_sources=[],
            model_name="test-model",
            reasoning_effort="medium",
            token_usage_input=8,
            token_usage_output=9,
        )

    monkeypatch.setattr(
        "app.services.analysis_orchestrator_service.generate_llm_result",
        fake_generate_llm_result,
    )
    monkeypatch.setattr(
        "app.services.analysis_orchestrator_service.generate_streamed_llm_result",
        fake_generate_streamed_llm_result,
    )

    async def run_test() -> None:
        result = await run_functional_multi_agent_analysis(
            session=SimpleNamespace(),
            session_row=SimpleNamespace(
                ts_code="600519.SH",
                topic="watchlist",
                use_web_search=True,
            ),
            instrument=SimpleNamespace(name="贵州茅台"),
            latest_snapshot=None,
            event_payloads=[],
            factor_weights=[],
        )

        hypothesis_role = next(
            role for role in result.pipeline_roles if role.role_key == "hypothesis_builder"
        )
        assert result.status == "partial"
        assert result.web_search_status == "unsupported"
        assert hypothesis_role.status == "partial"
        assert hypothesis_role.failure_type == "RuntimeError"

    asyncio.run(run_test())
