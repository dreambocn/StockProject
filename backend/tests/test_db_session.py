from app.core.settings import Settings
from app.db.session import build_engine_options


def test_build_engine_options_uses_conservative_pool_defaults() -> None:
    settings = Settings(
        _env_file=None,
        postgres_jdbc_url="jdbc:postgresql://127.0.0.1:5432/stockproject",
        postgres_user="postgres",
        postgres_password="postgres",
        redis_jdbc_url="jdbc:redis://127.0.0.1:6379/0",
        db_pool_size=1,
        db_max_overflow=0,
        db_pool_timeout_seconds=15,
    )

    engine_options = build_engine_options(settings)

    assert engine_options["pool_pre_ping"] is True
    assert engine_options["pool_size"] == 1
    assert engine_options["max_overflow"] == 0
    assert engine_options["pool_timeout"] == 15


def test_build_engine_options_adds_search_path_when_schema_exists() -> None:
    settings = Settings(
        _env_file=None,
        postgres_jdbc_url="jdbc:postgresql://127.0.0.1:5432/stockproject.public",
        postgres_user="postgres",
        postgres_password="postgres",
        redis_jdbc_url="jdbc:redis://127.0.0.1:6379/0",
    )

    engine_options = build_engine_options(settings)

    assert engine_options["connect_args"] == {
        "server_settings": {"search_path": "public"}
    }
