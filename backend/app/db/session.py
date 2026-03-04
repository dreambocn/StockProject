from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.settings import get_settings


settings = get_settings()
engine_options: dict[str, object] = {
    # 连接借出前先探活，降低长连接失效导致的首次请求失败概率。
    "pool_pre_ping": True,
}
if settings.postgres_schema:
    # 显式设置 search_path，确保多 schema 场景下 ORM 命中目标 schema。
    engine_options["connect_args"] = {
        "server_settings": {"search_path": settings.postgres_schema}
    }

engine = create_async_engine(settings.postgres_async_dsn, **engine_options)
SessionLocal = async_sessionmaker(
    bind=engine, class_=AsyncSession, expire_on_commit=False
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    # 会话生命周期与请求绑定，保证事务边界清晰且连接可回收。
    async with SessionLocal() as session:
        yield session
