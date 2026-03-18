import asyncio

from sqlalchemy import select
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.settings import Settings
from app.db.init_db import (
    ensure_database_exists,
    ensure_initial_admin_user,
    ensure_postgres_schema_exists,
    ensure_schema_for_engine,
)
from app.models.user import User


def test_ensure_schema_creates_required_tables(tmp_path) -> None:
    db_file = tmp_path / "schema-check.db"
    db_url = f"sqlite+aiosqlite:///{db_file.as_posix()}"
    engine = create_async_engine(db_url)

    async def run_test() -> None:
        async with engine.begin() as connection:
            before_tables = await connection.run_sync(
                lambda sync_conn: inspect(sync_conn).get_table_names()
            )

        assert "users" not in before_tables

        await ensure_schema_for_engine(engine)

        async with engine.begin() as connection:
            after_tables = await connection.run_sync(
                lambda sync_conn: inspect(sync_conn).get_table_names()
            )

        assert "users" in after_tables
        assert "news_events" in after_tables

        await engine.dispose()

    asyncio.run(run_test())


def test_ensure_database_exists_creates_missing_database() -> None:
    class FakeConnection:
        def __init__(self) -> None:
            self.executed: list[str] = []
            self.closed = False

        async def fetch(self, _: str):
            return [{"datname": "postgres"}, {"datname": "DreamBoDB"}]

        async def execute(self, sql: str):
            self.executed.append(sql)

        async def close(self):
            self.closed = True

    fake_connection = FakeConnection()

    async def fake_connector(**kwargs):
        assert kwargs["database"] == "postgres"
        return fake_connection

    settings = Settings(
        postgres_jdbc_url="jdbc:postgresql://127.0.0.1:5432/stockdb",
        postgres_user="postgres",
        postgres_password="postgres",
        redis_jdbc_url="jdbc:redis://127.0.0.1:6379/0",
    )

    asyncio.run(ensure_database_exists(settings, connector=fake_connector))

    assert fake_connection.executed == ['create database "stockdb"']
    assert fake_connection.closed is True


def test_ensure_postgres_schema_exists_creates_missing_schema() -> None:
    class FakeConnection:
        def __init__(self) -> None:
            self.executed: list[str] = []
            self.closed = False

        async def fetchval(self, _: str, __: str):
            return None

        async def execute(self, sql: str):
            self.executed.append(sql)

        async def close(self):
            self.closed = True

    fake_connection = FakeConnection()

    async def fake_connector(**kwargs):
        assert kwargs["database"] == "DreamBoDB"
        return fake_connection

    settings = Settings(
        postgres_jdbc_url="jdbc:postgresql://127.0.0.1:5432/DreamBoDB.stockdb",
        postgres_user="postgres",
        postgres_password="postgres",
        redis_jdbc_url="jdbc:redis://127.0.0.1:6379/0",
    )

    asyncio.run(ensure_postgres_schema_exists(settings, connector=fake_connector))

    assert fake_connection.executed == ['create schema "stockdb"']
    assert fake_connection.closed is True


def test_ensure_initial_admin_user_creates_seed_admin(tmp_path) -> None:
    db_file = tmp_path / "seed-admin.db"
    db_url = f"sqlite+aiosqlite:///{db_file.as_posix()}"
    engine = create_async_engine(db_url)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    settings = Settings(
        postgres_jdbc_url="jdbc:postgresql://127.0.0.1:5432/DreamBoDB.stockdb",
        postgres_user="postgres",
        postgres_password="postgres",
        redis_jdbc_url="jdbc:redis://127.0.0.1:6379/0",
        init_admin_username="admin-root",
        init_admin_email="admin-root@example.com",
        init_admin_password="StrongP@ss1",
    )

    async def run_test() -> None:
        await ensure_schema_for_engine(engine)
        await ensure_initial_admin_user(settings, session_factory=session_maker)

        async with session_maker() as session:
            result = await session.execute(
                select(User).where(User.username == "admin-root")
            )
            admin = result.scalar_one_or_none()

        assert admin is not None
        assert admin.email == "admin-root@example.com"
        assert admin.user_level == "admin"

        await engine.dispose()

    asyncio.run(run_test())
