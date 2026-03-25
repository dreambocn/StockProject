from dataclasses import dataclass
from statistics import mean, pstdev


@dataclass
class EventLinkResult:
    window_return_pct: float
    window_volatility: float
    abnormal_volume_ratio: float
    correlation_score: float
    confidence: str
    link_status: str


def _calculate_return_pct(prices: list[float]) -> float:
    if not prices or prices[0] == 0:
        # 空样本或基准为 0 时无法计算收益，直接回落 0。
        return 0.0
    return (prices[-1] - prices[0]) / prices[0] * 100


def _calculate_volatility(pct_changes: list[float]) -> float:
    if len(pct_changes) <= 1:
        # 只有一个点时波动率不可用，按 0 处理。
        return 0.0
    return pstdev(pct_changes)


def _calculate_abnormal_volume(volumes: list[float]) -> float:
    if not volumes:
        return 0.0
    avg = mean(volumes)
    if avg <= 0:
        # 均值为 0 代表无量能，避免除零。
        return 0.0
    return max(volumes) / avg


def _correlation_score(window_return_pct: float, sentiment_score: float) -> float:
    base = 0.7 * min(abs(window_return_pct) / 10, 1.0)
    sentiment_component = 0.3 * abs(sentiment_score)
    score = base + sentiment_component
    return max(0.0, min(score, 1.0))


def _confidence_label(window_days: int, label_count: int) -> str:
    # 置信度只依赖窗口长度和标签命中数量，避免引入不稳定指标。
    if window_days >= 5 and label_count > 0:
        return "high"
    if window_days >= 3:
        return "medium"
    return "low"


def build_event_link_result(
    prices: list[dict[str, float]],
    sentiment_score: float,
    label_count: int,
) -> EventLinkResult:
    """
    从价格窗口数据计算事件关联指标，供分析服务消费。
    """
    sorted_prices = sorted(prices, key=lambda item: item["trade_date"])
    closes = [item["close"] for item in sorted_prices if item["close"] is not None]
    pct_changes = []
    for prev, curr in zip(closes, closes[1:]):
        if prev == 0:
            pct_changes.append(0.0)
        else:
            pct_changes.append((curr - prev) / prev * 100)

    window_return_pct = _calculate_return_pct(closes)
    window_volatility = _calculate_volatility(pct_changes)
    abnormal_volume_ratio = _calculate_abnormal_volume(
        [item["vol"] for item in sorted_prices if item.get("vol") is not None]
    )
    correlation_score = _correlation_score(window_return_pct, sentiment_score)
    confidence = _confidence_label(len(sorted_prices), label_count)

    return EventLinkResult(
        window_return_pct=window_return_pct,
        window_volatility=window_volatility,
        abnormal_volume_ratio=abnormal_volume_ratio,
        correlation_score=correlation_score,
        confidence=confidence,
        link_status="linked",
    )
