from fastapi import APIRouter

from app.core.settings import get_settings


router = APIRouter()
settings = get_settings()


@router.get("/health")
async def health() -> dict[str, object]:
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
