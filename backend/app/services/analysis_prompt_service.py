from typing import Iterable

from app.services.factor_weight_service import FactorWeight


def build_analysis_system_instruction() -> str:
    return "\n".join(
        [
            "你是股票分析工作台的中文研判助手，需要以事件点评快报的研报口吻输出内容。",
            "你只能输出面向终端用户的股票分析 Markdown 内容。",
            "整体风格要像卖方研究团队发布的事件点评快报：结论先行、措辞克制、判断明确、证据充分。",
            "不要输出过程说明、思考步骤、工具调用、搜索动作、自我计划或角色描述。",
            "不要提及仓库、目录、文件、代码、提示词、系统指令或任何内部执行过程。",
            "避免口语化表达、避免网络化措辞、避免使用第一人称。",
            "如果证据不足，请直接说明不确定性，但仍保持分析报告口吻。",
        ]
    )


def build_analysis_prompt(
    ts_code: str,
    instrument_name: str | None,
    events: Iterable[dict[str, object]],
    factor_weights: Iterable[FactorWeight],
) -> str:
    """
    组合股票、事件和因子信息，生成中文 prompt 提供给大模型。
    """
    header = (
        f"请针对 {ts_code}（{instrument_name or '未知标的'}）输出一份事件点评快报风格的中文 Markdown 股票分析简报。"
    )
    event_lines = []
    for event in events:
        title = event.get("title") or "未知事件"
        published_at = event.get("published_at") or "未知时间"
        sentiment_label = event.get("sentiment_label") or "unknown"
        correlation_score = event.get("correlation_score")
        correlation_text = (
            f"{float(correlation_score):.2f}"
            if isinstance(correlation_score, (int, float))
            else "暂无"
        )
        event_lines.append(
            "- "
            f"{title}（类型：{event.get('event_type', 'news')}，"
            f"情绪：{sentiment_label}，关联度：{correlation_text}，时间：{published_at}）"
        )

    factor_lines = []
    for factor in factor_weights:
        factor_lines.append(
            f"- {factor.factor_label}：权重 {factor.weight:.2f}，方向 {factor.direction}，理由：{factor.reason}"
        )

    return "\n".join(
        [
            header,
            "输出要求：",
            "1. 使用事件点评快报的研报口吻，结论先行，不要寒暄。",
            "2. 仅使用以下二级标题：## 核心判断、## 关键证据、## 风险提示。",
            "3. 第一段先给出方向性判断，再说明主要驱动，不要先复述输入数据。",
            "4. 语言要专业、克制、凝练，避免口语化表达，避免使用第一人称。",
            "5. 风险提示要体现条件、边界和不确定性，避免泛泛而谈。",
            "6. 不要输出“准备先查看”“我将”“先分析”“工具调用”“查看仓库/目录/文件”等过程文本。",
            "7. 若联网增强可用，只能吸收公开信息，不要描述搜索过程。",
            "关键事件：",
            *event_lines[:3],
            "因子权重：",
            *factor_lines,
            "请输出面向投资者、接近卖方研究事件点评快报风格的中文分析 Markdown。",
        ]
    )
