from datetime import datetime, UTC
from typing import Any


async def fetch_policy_events() -> list[dict[str, Any]]:
    """
    模拟从政策数据源拉取事件，为 P0 提供最小可用政策事件流。
    """
    now = datetime.now(UTC)
    # 简单返回固定示例，后续可替换为真实网关
    return [
        {
            "title": "证监会发布加强资本市场监管通知",
            "summary": "规范数据中介业务，提升市场透明度",
            "published_at": now.isoformat(),
            "link": "https://example.com/policy/1",
        }
    ]
