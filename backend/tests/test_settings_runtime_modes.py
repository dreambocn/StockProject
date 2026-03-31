from app.core.settings import Settings


def test_settings_runtime_mode_defaults() -> None:
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
