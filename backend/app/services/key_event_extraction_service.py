from typing import List

KEYWORD_MAP: dict[str, tuple[str, ...]] = {
    "policy": ("政策", "监管", "指导意见", "意见稿"),
    "regulation": ("监管", "条例", "整改", "合规"),
    "announcement": ("公告", "披露", "发布", "通告"),
    "earnings": ("业绩", "利润", "营收", "EPS"),
    "industry": ("行业", "板块", "产业", "集成电路"),
    "commodity": ("原油", "黄金", "煤炭", "有色", "大宗"),
    "capital_flow": ("资金", "融资", "增持", "减持", "北上"),
    "risk": ("风险", "纠纷", "诉讼", "处罚"),
}


def extract_key_event_types(title: str, summary: str | None) -> List[str]:
    """
    根据关键词识别事件类型，最多保留 3 个标签。
    """
    text = f"{title} {summary or ''}".lower()
    labels: List[str] = []

    # 按优先级顺序匹配，最多返回 3 个标签，避免前端标签过多失焦。
    for label, keywords in KEYWORD_MAP.items():
        for keyword in keywords:
            if keyword in text and label not in labels:
                labels.append(label)
                break
        if len(labels) >= 3:
            break

    # 未命中任何关键词时回落为通用 news 标签。
    return labels or ["news"]
