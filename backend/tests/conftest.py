import asyncio
import os
from pathlib import Path
from typing import Callable

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine

from app.db.base import Base


_MANAGED_SQLITE_ENGINES: dict[str, list[AsyncEngine]] = {}


def _current_test_key() -> str:
    return os.environ.get("PYTEST_CURRENT_TEST", "__unknown_test__")


def _register_sqlite_engine(engine: AsyncEngine) -> None:
    _MANAGED_SQLITE_ENGINES.setdefault(_current_test_key(), []).append(engine)


async def _create_sqlite_schema(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


def init_sqlite_schema(engine: AsyncEngine) -> None:
    """统一初始化 SQLite 测试库结构，保持现有同步测试风格。"""
    asyncio.run(_create_sqlite_schema(engine))


def build_sqlite_test_context(
    tmp_path: Path,
    filename: str,
) -> tuple[AsyncEngine, async_sessionmaker]:
    db_path = tmp_path / filename
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path.as_posix()}")
    _register_sqlite_engine(engine)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
def sqlite_test_db_factory(
    tmp_path: Path,
) -> Callable[[str], tuple[AsyncEngine, async_sessionmaker]]:
    def _factory(filename: str) -> tuple[AsyncEngine, async_sessionmaker]:
        return build_sqlite_test_context(tmp_path, filename)

    return _factory


@pytest.fixture(autouse=True)
def _dispose_sqlite_test_engines() -> None:
    yield

    async def _dispose_managed_engines() -> None:
        # 关键清理：aiosqlite 连接背后有后台线程，必须在测试结束前显式释放，
        # 避免 asyncio.run() 关闭事件循环后线程再回调旧 loop 触发 warning。
        for engine in reversed(_MANAGED_SQLITE_ENGINES.pop(_current_test_key(), [])):
            await engine.dispose()

    asyncio.run(_dispose_managed_engines())
