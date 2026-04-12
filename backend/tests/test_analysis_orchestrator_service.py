import json
from datetime import UTC, date, datetime
from decimal import Decimal

from app.services.analysis_orchestrator_service import (
    build_functional_prompt_version,
    to_json_safe_payload,
)


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
