from dataclasses import dataclass


@dataclass
class SentimentResult:
    label: str
    score: float


def analyze_news_sentiment(title: str, summary: str | None) -> SentimentResult:
    """
    通过简单关键词规则推断新闻情绪，与上线的阈值保持一致。
    """
    text = f"{title} {summary or ''}".lower()
    score = 0.0
    positive_keywords = ("利好", "超预期", "上涨", "增长", "改善", "提升")
    negative_keywords = ("下滑", "警告", "下降", "风险", "亏损", "拖累")

    for keyword in positive_keywords:
        if keyword in text:
            score += 0.25
    for keyword in negative_keywords:
        if keyword in text:
            score -= 0.25

    score = max(min(score, 1.0), -1.0)
    if score >= 0.2:
        label = "positive"
    elif score <= -0.2:
        label = "negative"
    else:
        label = "neutral"

    return SentimentResult(label=label, score=score)
