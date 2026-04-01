from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.settings import Settings, get_settings


def build_engine_options(settings: Settings) -> dict[str, object]:
    engine_options: dict[str, object] = {
        # 连接借出前先探活，降低长连接失效导致的首次请求失败概率。
        "pool_pre_ping": True,
        # 开发环境默认使用保守连接池，避免 API / Worker 多进程叠加打满远端数据库连接数。
        "pool_size": settings.db_pool_size,
        "max_overflow": settings.db_max_overflow,
        "pool_timeout": settings.db_pool_timeout_seconds,
    }
    if settings.postgres_schema:
        # 显式设置 search_path，确保多 schema 场景下 ORM 命中目标 schema。
        engine_options["connect_args"] = {
            "server_settings": {"search_path": settings.postgres_schema}
        }
    return engine_options


settings = get_settings()
engine_options = build_engine_options(settings)

engine = create_async_engine(settings.postgres_async_dsn, **engine_options)
SessionLocal = async_sessionmaker(
    # 关闭提交后过期，避免后续响应序列化时触发隐式刷新。
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    # 会话生命周期与请求绑定，保证事务边界清晰且连接可回收。
    async with SessionLocal() as session:
        yield session
