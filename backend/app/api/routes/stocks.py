from fastapi import APIRouter


router = APIRouter()


@router.get("/stocks")
async def stocks() -> list[dict[str, str | float]]:
    # 临时示例数据接口：用于前端联调，后续会替换为真实行情源。
    return [
        {"symbol": "AAPL", "name": "Apple", "price": 213.48, "change": 1.42},
        {"symbol": "TSLA", "name": "Tesla", "price": 256.74, "change": -0.95},
        {"symbol": "NVDA", "name": "NVIDIA", "price": 917.32, "change": 2.16},
    ]
