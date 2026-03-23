from app.services.key_event_extraction_service import extract_key_event_types


def test_key_event_extraction_limits_three_tags() -> None:
    labels = extract_key_event_types(
        "政策、监管、公告、风险",
        "行业、资金与合规逻辑",
    )
    assert len(labels) <= 3


def test_key_event_extraction_captures_policy_and_regulation() -> None:
    labels = extract_key_event_types(
        "监管新规释放政策信号",
        "鼓励高端制造与绿色能源",
    )
    assert "policy" in labels or "regulation" in labels
