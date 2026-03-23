from app.services.event_link_service import build_event_link_result


def test_event_link_service_produces_expected_keys() -> None:
    price_rows = [
        {"trade_date": "2026-03-01", "close": 10.0, "vol": 1000.0},
        {"trade_date": "2026-03-02", "close": 10.5, "vol": 1200.0},
        {"trade_date": "2026-03-03", "close": 10.2, "vol": 1100.0},
    ]
    result = build_event_link_result(price_rows, sentiment_score=0.3, label_count=2)

    assert hasattr(result, "window_return_pct")
    assert hasattr(result, "window_volatility")
    assert hasattr(result, "abnormal_volume_ratio")
    assert 0.0 <= result.correlation_score <= 1.0
    assert result.confidence in {"high", "medium", "low"}
