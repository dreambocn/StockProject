from functools import lru_cache
from urllib.parse import quote, urlparse

from pydantic_settings import BaseSettings, SettingsConfigDict


def _remove_jdbc_prefix(url: str) -> str:
    if url.startswith("jdbc:"):
        return url[5:]

    return url


class Settings(BaseSettings):
    postgres_jdbc_url: str = "jdbc:postgresql://127.0.0.1:5432/postgres"
    postgres_user: str = "postgres"
    postgres_password: str = "postgres"
    redis_jdbc_url: str = "jdbc:redis://127.0.0.1:6379/0"
    jwt_secret_key: str = "change-this-secret-key-to-32-chars-min"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7
    postgres_maintenance_db: str = "postgres"
    db_auto_create_database: bool = True
    db_auto_create_tables: bool = True
    login_captcha_threshold: int = 2
    login_fail_window_seconds: int = 900
    captcha_ttl_seconds: int = 300
    captcha_length: int = 4

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def postgres_host(self) -> str:
        return (
            urlparse(_remove_jdbc_prefix(self.postgres_jdbc_url)).hostname
            or "127.0.0.1"
        )

    @property
    def postgres_port(self) -> int:
        return urlparse(_remove_jdbc_prefix(self.postgres_jdbc_url)).port or 5432

    @property
    def postgres_database(self) -> str:
        path = urlparse(_remove_jdbc_prefix(self.postgres_jdbc_url)).path.lstrip("/")
        database_path = path or "postgres"
        if "." in database_path:
            database_name, _schema_name = database_path.split(".", 1)
            return database_name or "postgres"

        return database_path

    @property
    def postgres_schema(self) -> str | None:
        path = urlparse(_remove_jdbc_prefix(self.postgres_jdbc_url)).path.lstrip("/")
        database_path = path or "postgres"
        if "." not in database_path:
            return None

        _database_name, schema_name = database_path.split(".", 1)
        if not schema_name:
            return None

        return schema_name

    @property
    def postgres_async_dsn(self) -> str:
        username = quote(self.postgres_user, safe="")
        password = quote(self.postgres_password, safe="")
        database = self.postgres_database
        return (
            f"postgresql+asyncpg://{username}:{password}@"
            f"{self.postgres_host}:{self.postgres_port}/{database}"
        )

    @property
    def redis_host(self) -> str:
        return (
            urlparse(_remove_jdbc_prefix(self.redis_jdbc_url)).hostname or "127.0.0.1"
        )

    @property
    def redis_port(self) -> int:
        return urlparse(_remove_jdbc_prefix(self.redis_jdbc_url)).port or 6379

    @property
    def redis_db(self) -> str:
        path = urlparse(_remove_jdbc_prefix(self.redis_jdbc_url)).path.lstrip("/")
        return path or "0"

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    @property
    def access_token_expire_seconds(self) -> int:
        return self.access_token_expire_minutes * 60

    @property
    def refresh_token_expire_seconds(self) -> int:
        return self.refresh_token_expire_days * 24 * 60 * 60


@lru_cache
def get_settings() -> Settings:
    return Settings()
