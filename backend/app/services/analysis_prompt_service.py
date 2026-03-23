from datetime import datetime
from typing import Iterable

from app.services.factor_weight_service import FactorWeight


def build_analysis_prompt(
    ts_code: str,
    instrument_name: str | None,
    events: Iterable[dict[str, object]],
    factor_weights: Iterable[FactorWeight],
) -> str:
    """
    组合股票、事件和因子信息，生成中文 prompt 提供给大模型。
    """
    header = f"请针对 {ts_code}（{instrument_name or '未知标的'}）生成波动分析："
    event_lines = []
    for event in events:
        title = event.get("title") or "未知事件"
        event_lines.append(f"- {title}（{event.get('event_type', 'news')}）")

    factor_lines = []
    for factor in factor_weights:
        factor_lines.append(
            f"{factor.factor_label}：{factor.weight:.2f}，方向 {factor.direction}"
        )

    return "\n".join(
        [
            header,
            "关键事件：",
            *event_lines[:3],
            "因子权重：",
            *factor_lines,
            "请输出中文摘要和风险提示。",
        ]
    )
