from app.core.settings import Settings


def test_settings_runtime_mode_defaults(monkeypatch) -> None:
    # 默认值测试必须忽略 CI 的 APP_ENV / bootstrap 配置，才能真正覆盖类内默认值。
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("DB_SCHEMA_BOOTSTRAP_MODE", raising=False)
    monkeypatch.delenv("INIT_ADMIN_ENABLED", raising=False)
    settings = Settings(_env_file=None)

    assert settings.app_env == "development"
    assert settings.db_schema_bootstrap_mode == "auto_apply"
    assert settings.init_admin_enabled is False
    assert settings.job_heartbeat_stale_seconds == 120
    assert settings.job_retention_days == 30


def test_settings_runtime_mode_accepts_non_dev_validate_only() -> None:
    settings = Settings(
        _env_file=None,
        app_env="production",
        db_schema_bootstrap_mode="validate_only",
        init_admin_enabled=False,
    )

    assert settings.app_env == "production"
    assert settings.db_schema_bootstrap_mode == "validate_only"
    assert settings.init_admin_enabled is False
