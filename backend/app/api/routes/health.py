from fastapi import APIRouter

from app.core.settings import get_settings


router = APIRouter()
settings = get_settings()


@router.get("/health")
async def health() -> dict[str, object]:
    # 当前健康检查返回配置视角信息，便于快速确认运行时参数。
    # 注意：这不是底层连接探针，不代表 PostgreSQL/Redis 一定可连通。
    return {
        "status": "ok",
        "services": {
            "postgres": {
                "host": settings.postgres_host,
                "port": settings.postgres_port,
                "database": settings.postgres_database,
            },
            "redis": {
                "host": settings.redis_host,
                "port": settings.redis_port,
                "db": settings.redis_db,
            },
        },
    }
