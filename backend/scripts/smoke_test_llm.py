import asyncio
import sys
from pathlib import Path


# 直接执行脚本时把 backend 根目录加入模块搜索路径，避免 `app.*` 导入失败。
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.llm_client_service import generate_llm_text


async def main() -> None:
    # 该脚本用于最小连通性验证：只要能稳定返回 OK，就说明模型配置和网关已可用。
    result = await generate_llm_text(
        "请只返回OK",
        max_output_tokens=32,
    )
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
