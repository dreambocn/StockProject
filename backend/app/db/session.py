from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.settings import get_settings


settings = get_settings()
engine_options: dict[str, object] = {
    "pool_pre_ping": True,
}
if settings.postgres_schema:
    engine_options["connect_args"] = {
        "server_settings": {"search_path": settings.postgres_schema}
    }

engine = create_async_engine(settings.postgres_async_dsn, **engine_options)
SessionLocal = async_sessionmaker(
    bind=engine, class_=AsyncSession, expire_on_commit=False
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session
