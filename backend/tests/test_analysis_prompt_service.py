from app.services.analysis_prompt_service import (
    build_analysis_prompt,
    build_analysis_system_instruction,
)
from app.services.factor_weight_service import FactorWeight


def test_build_analysis_system_instruction_uses_event_note_tone() -> None:
    system_instruction = build_analysis_system_instruction()

    assert "事件点评快报" in system_instruction
    assert "研报口吻" in system_instruction
    assert "不要输出过程说明" in system_instruction


def test_build_analysis_prompt_requests_research_note_structure() -> None:
    prompt = build_analysis_prompt(
        ts_code="600519.SH",
        instrument_name="贵州茅台",
        events=[
            {
                "title": "白酒消费政策优化",
                "event_type": "policy",
                "published_at": "2026-03-24T09:30:00Z",
                "sentiment_label": "positive",
                "correlation_score": 0.86,
            }
        ],
        factor_weights=[
            FactorWeight(
                factor_key="policy",
                factor_label="政策",
                weight=0.58,
                direction="positive",
                evidence=["监管边际改善"],
                reason="政策边际改善带来风险偏好修复",
            )
        ],
    )

    assert "事件点评快报" in prompt
    assert "结论先行" in prompt
    assert "研报口吻" in prompt
    assert "避免口语化表达" in prompt
    assert "## 核心判断" in prompt
    assert "## 关键证据" in prompt
    assert "## 风险提示" in prompt


def test_build_analysis_prompt_supports_evidence_first_profile() -> None:
    prompt = build_analysis_prompt(
        ts_code="600519.SH",
        instrument_name="贵州茅台",
        events=[
            {
                "title": "白酒消费政策优化",
                "event_type": "policy",
                "published_at": "2026-03-24T09:30:00Z",
                "sentiment_label": "positive",
                "correlation_score": 0.86,
            }
        ],
        factor_weights=[
            FactorWeight(
                factor_key="policy",
                factor_label="政策",
                weight=0.58,
                direction="positive",
                evidence=["监管边际改善"],
                reason="政策边际改善带来风险偏好修复",
            )
        ],
        prompt_profile_key="evidence_first_v2",
    )
    system_instruction = build_analysis_system_instruction(
        prompt_profile_key="evidence_first_v2"
    )

    assert "结构化证据优先" in prompt
    assert "联网补证" in prompt
    assert "已验证事实" in system_instruction
