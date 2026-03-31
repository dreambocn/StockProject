import asyncio

from app.core.settings import Settings
from app.db import init_db


def test_ensure_database_schema_auto_apply_runs_bootstrap_and_seed(monkeypatch) -> None:
    called: list[str] = []

    settings = Settings(
        _env_file=None,
        app_env="development",
        db_schema_bootstrap_mode="auto_apply",
        init_admin_enabled=True,
    )

    async def fake_ensure_database_exists(current_settings):
        assert current_settings is settings
        called.append("ensure_database_exists")

    async def fake_ensure_postgres_schema_exists(current_settings):
        assert current_settings is settings
        called.append("ensure_postgres_schema_exists")

    async def fake_upgrade_database_schema(*, settings, target_engine):
        assert target_engine == "engine-token"
        called.append("upgrade_database_schema")

    async def fake_validate_database_schema(*, settings, target_engine):
        called.append("validate_database_schema")

    async def fake_ensure_initial_admin_user(current_settings, session_factory=None):
        assert current_settings is settings
        assert session_factory == "session-factory-token"
        called.append("ensure_initial_admin_user")

    monkeypatch.setattr(init_db, "ensure_database_exists", fake_ensure_database_exists)
    monkeypatch.setattr(
        init_db,
        "ensure_postgres_schema_exists",
        fake_ensure_postgres_schema_exists,
    )
    monkeypatch.setattr(init_db, "upgrade_database_schema", fake_upgrade_database_schema)
    monkeypatch.setattr(init_db, "validate_database_schema", fake_validate_database_schema)
    monkeypatch.setattr(
        init_db,
        "ensure_initial_admin_user",
        fake_ensure_initial_admin_user,
    )

    asyncio.run(
        init_db.ensure_database_schema(
            settings=settings,
            target_engine="engine-token",
            session_factory="session-factory-token",
        )
    )

    assert called == [
        "ensure_database_exists",
        "ensure_postgres_schema_exists",
        "upgrade_database_schema",
        "ensure_initial_admin_user",
    ]


def test_ensure_database_schema_validate_only_skips_bootstrap_and_seed(monkeypatch) -> None:
    called: list[str] = []

    settings = Settings(
        _env_file=None,
        app_env="production",
        db_schema_bootstrap_mode="validate_only",
        init_admin_enabled=False,
    )

    async def fake_ensure_database_exists(current_settings):
        called.append("ensure_database_exists")

    async def fake_ensure_postgres_schema_exists(current_settings):
        called.append("ensure_postgres_schema_exists")

    async def fake_upgrade_database_schema(*, settings, target_engine):
        called.append("upgrade_database_schema")

    async def fake_validate_database_schema(*, settings, target_engine):
        assert target_engine == "engine-token"
        called.append("validate_database_schema")

    async def fake_ensure_initial_admin_user(current_settings, session_factory=None):
        called.append("ensure_initial_admin_user")

    monkeypatch.setattr(init_db, "ensure_database_exists", fake_ensure_database_exists)
    monkeypatch.setattr(
        init_db,
        "ensure_postgres_schema_exists",
        fake_ensure_postgres_schema_exists,
    )
    monkeypatch.setattr(init_db, "upgrade_database_schema", fake_upgrade_database_schema)
    monkeypatch.setattr(init_db, "validate_database_schema", fake_validate_database_schema)
    monkeypatch.setattr(
        init_db,
        "ensure_initial_admin_user",
        fake_ensure_initial_admin_user,
    )

    asyncio.run(
        init_db.ensure_database_schema(
            settings=settings,
            target_engine="engine-token",
            session_factory="session-factory-token",
        )
    )

    assert called == ["validate_database_schema"]
