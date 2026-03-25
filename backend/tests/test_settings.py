import pytest

from app.core.settings import Settings


def test_settings_build_postgres_async_dsn() -> None:
    settings = Settings(
        _env_file=None,
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
        _env_file=None,
        postgres_jdbc_url="jdbc:postgresql://192.168.31.199:2143/DreamBoDB",
        postgres_user="dreambo",
        postgres_password="syb/20031122",
        redis_jdbc_url="jdbc:redis://192.168.31.199:6379/0",
    )

    assert settings.redis_url == "redis://192.168.31.199:6379/0"


def test_settings_build_redis_url_with_auth_from_env() -> None:
    settings = Settings(
        _env_file=None,
        redis_jdbc_url="jdbc:redis://192.168.31.199:6379/0",
        redis_username="default",
        redis_password="p@ss/word",
    )

    assert settings.redis_url == "redis://default:p%40ss%2Fword@192.168.31.199:6379/0"


def test_settings_parse_database_and_schema_from_jdbc_path() -> None:
    settings = Settings(
        _env_file=None,
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
    settings = Settings(_env_file=None)

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
    assert settings.cors_allow_origins_list == [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    assert settings.stock_related_news_cache_ttl_seconds == 3600
    assert settings.hot_news_cache_ttl_seconds == 3600
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


def test_settings_llm_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.llm_base_url == "https://aixj.vip"
    assert settings.llm_wire_api == "responses"
    assert settings.llm_api_key == ""
    assert settings.llm_model == "gpt-5.1-codex-mini"
    assert settings.llm_reasoning_effort == "high"


def test_settings_accept_custom_llm_values() -> None:
    settings = Settings(
        _env_file=None,
        llm_base_url="https://example.com/llm",
        llm_wire_api="responses",
        llm_api_key="test-key",
        llm_model="gpt-5.1-codex-mini",
        llm_reasoning_effort="medium",
    )

    assert settings.llm_base_url == "https://example.com/llm"
    assert settings.llm_wire_api == "responses"
    assert settings.llm_api_key == "test-key"
    assert settings.llm_model == "gpt-5.1-codex-mini"
    assert settings.llm_reasoning_effort == "medium"


def test_settings_analysis_event_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.analysis_generation_event_limit == 30
    assert settings.analysis_generation_candidate_pool_multiplier == 4
    assert settings.analysis_generation_stock_quota == 12
    assert settings.analysis_generation_policy_quota == 8
    assert settings.analysis_generation_hot_quota == 10
    assert settings.analysis_summary_event_limit == 20
    assert settings.analysis_summary_candidate_pool_multiplier == 4


def test_settings_reject_analysis_quota_sum_greater_than_limit() -> None:
    with pytest.raises(ValueError, match="ANALYSIS_GENERATION_.*QUOTA"):
        Settings(
            _env_file=None,
            analysis_generation_event_limit=20,
            analysis_generation_stock_quota=12,
            analysis_generation_policy_quota=8,
            analysis_generation_hot_quota=10,
        )
