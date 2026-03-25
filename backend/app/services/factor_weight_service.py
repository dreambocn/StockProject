from dataclasses import dataclass
from typing import List


@dataclass
class FactorWeight:
    factor_key: str
    factor_label: str
    weight: float
    direction: str
    evidence: List[str]
    reason: str


def calculate_factor_weights(events: list[dict[str, object]]) -> List[FactorWeight]:
    """
    按 Policy / Announcement / News / Sentiment 四类统计事件权重。
    """
    base_counters = {
        "policy": 0,
        "announcement": 0,
        "news": 0,
        "sentiment": 0,
    }
    positive_sentiments = 0
    negative_sentiments = 0

    for event in events:
        event_type = str(event.get("event_type") or "news")
        if event_type in base_counters:
            base_counters[event_type] += 1
        else:
            base_counters["news"] += 1

        sentiment = float(event.get("sentiment_score") or 0.0)
        if sentiment >= 0.2:
            positive_sentiments += 1
        elif sentiment <= -0.2:
            negative_sentiments += 1

    # 使用事件占比作为基础权重，情绪信号单独作为补充因子。
    total = sum(base_counters.values()) or 1
    sentiment_signal = positive_sentiments - negative_sentiments
    weights: List[FactorWeight] = []
    raw_weights: list[tuple[str, str, float, str, list[str], str]] = []

    for key, label in (
        ("policy", "政策"),
        ("announcement", "公告"),
        ("news", "新闻"),
    ):
        fraction = base_counters[key] / total
        direction = "positive" if sentiment_signal >= 0 else "negative"
        raw_weights.append(
            (
                key,
                label,
                fraction,
                direction,
                [f"事件数量：{base_counters[key]}"],
                f"基于{label}事件占比确定",
            )
        )

    sentiment_weight = min(abs(sentiment_signal) / max(total, 1), 1.0)
    direction = "positive" if sentiment_signal >= 0 else "negative"
    raw_weights.append(
        (
            "sentiment",
            "情绪",
            sentiment_weight,
            direction,
            [f"正负情绪差：{sentiment_signal}"],
            "情绪倾向强弱决定",
        )
    )

    # 归一化确保权重和为 1，避免下游渲染出现比例异常。
    normalization_base = sum(item[2] for item in raw_weights) or 1.0
    for factor_key, factor_label, raw_weight, factor_direction, evidence, reason in raw_weights:
        weights.append(
            FactorWeight(
                factor_key=factor_key,
                factor_label=factor_label,
                weight=raw_weight / normalization_base,
                direction=factor_direction,
                evidence=evidence,
                reason=reason,
            )
        )

    return weights
