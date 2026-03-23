from app.services.factor_weight_service import calculate_factor_weights


def test_factor_weight_service_outputs_four_factors() -> None:
    events = [
        {"event_type": "policy", "sentiment_score": 0.3},
        {"event_type": "announcement", "sentiment_score": -0.1},
        {"event_type": "news", "sentiment_score": 0.0},
    ]
    weights = calculate_factor_weights(events)
    assert len(weights) == 4
    assert any(weight.factor_key == "policy" for weight in weights)
    assert any(weight.factor_key == "sentiment" for weight in weights)


def test_factor_weight_service_normalizes_total_weight() -> None:
    events = [
        {"event_type": "policy", "sentiment_score": 0.8},
        {"event_type": "policy", "sentiment_score": 0.5},
        {"event_type": "announcement", "sentiment_score": -0.4},
        {"event_type": "news", "sentiment_score": 0.0},
    ]

    weights = calculate_factor_weights(events)

    total_weight = sum(item.weight for item in weights)
    assert round(total_weight, 6) == 1.0
