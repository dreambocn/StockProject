from app.services.news_sentiment_service import analyze_news_sentiment


def test_sentiment_service_returns_positive_label_for_beneficial_news() -> None:
    result = analyze_news_sentiment(
        "公司业绩大增、利润超预期",
        "市场反应积极，销量创新高",
    )
    assert result.label == "positive"
    assert result.score >= 0.2


def test_sentiment_service_returns_negative_label_for_adverse_news() -> None:
    result = analyze_news_sentiment(
        "行业需求下滑",
        "供应链风险和盈利下行压力显著",
    )
    assert result.label == "negative"
    assert result.score <= -0.2
