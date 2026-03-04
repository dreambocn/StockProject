import pytest

from app.core.settings import Settings


def test_settings_build_postgres_async_dsn() -> None:
    settings = Settings(
        postgres_jdbc_url="jdbc:postgresql://192.168.31.199:2143/DreamBoDB",
        postgres_user="dreambo",
        postgres_password="syb/20031122",
        redis_jdbc_url="jdbc:redis://192.168.31.199:6379/0",
    )

    assert (
        settings.postgres_async_dsn
        == "postgresql+asyncpg://dreambo:syb%2F20031122@192.168.31.199:2143/DreamBoDB"
    )


def test_settings_build_redis_url() -> None:
    settings = Settings(
        postgres_jdbc_url="jdbc:postgresql://192.168.31.199:2143/DreamBoDB",
        postgres_user="dreambo",
        postgres_password="syb/20031122",
        redis_jdbc_url="jdbc:redis://192.168.31.199:6379/0",
    )

    assert settings.redis_url == "redis://192.168.31.199:6379/0"


def test_settings_parse_database_and_schema_from_jdbc_path() -> None:
    settings = Settings(
        postgres_jdbc_url="jdbc:postgresql://192.168.31.199:2143/DreamBoDB.stockdb",
        postgres_user="dreambo",
        postgres_password="syb/20031122",
        redis_jdbc_url="jdbc:redis://192.168.31.199:6379/0",
    )

    assert settings.postgres_database == "DreamBoDB"
    assert settings.postgres_schema == "stockdb"
    assert (
        settings.postgres_async_dsn
        == "postgresql+asyncpg://dreambo:syb%2F20031122@192.168.31.199:2143/DreamBoDB"
    )


def test_settings_captcha_defaults() -> None:
    settings = Settings()

    assert settings.login_captcha_threshold == 2
    assert settings.login_fail_window_seconds == 900
    assert settings.captcha_ttl_seconds == 300
    assert settings.captcha_length == 4
    assert settings.email_code_ttl_seconds == 300
    assert settings.email_code_cooldown_seconds == 60
    assert settings.email_code_length == 6
    assert settings.email_code_ip_limit_per_minute == 10
    assert settings.email_code_ip_limit_per_day == 200
    assert settings.email_code_ip_block_seconds == 900
    assert settings.trust_proxy_headers is False
    assert settings.trusted_proxy_ips_list == []


def test_settings_parse_cors_allow_origins_normalization() -> None:
    settings = Settings(
        cors_allow_origins=" http://localhost:5173, https://app.example.com ,http://localhost:5173 ",
    )

    assert settings.cors_allow_origins_list == [
        "http://localhost:5173",
        "https://app.example.com",
    ]


def test_settings_reject_wildcard_with_credentials_enabled() -> None:
    settings = Settings(
        cors_allow_origins="https://app.example.com,*",
        cors_allow_credentials=True,
    )

    with pytest.raises(ValueError, match="CORS_ALLOW_ORIGINS"):
        _ = settings.cors_allow_origins_list


def test_settings_allow_empty_origins_with_credentials_enabled() -> None:
    settings = Settings(
        cors_allow_origins="",
        cors_allow_credentials=True,
    )

    assert settings.cors_allow_origins_list == []


def test_settings_parse_trusted_proxy_ips_normalization() -> None:
    settings = Settings(
        trusted_proxy_ips=" 10.0.0.1, 10.0.0.2 ,10.0.0.1 ",
    )

    assert settings.trusted_proxy_ips_list == ["10.0.0.1", "10.0.0.2"]
