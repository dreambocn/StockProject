from functools import lru_cache
from urllib.parse import quote, urlparse

from pydantic_settings import BaseSettings, SettingsConfigDict


def _remove_jdbc_prefix(url: str) -> str:
    # 兼容历史 JDBC 风格配置，内部统一转换为标准 URL 解析。
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
    email_code_ttl_seconds: int = 300
    email_code_cooldown_seconds: int = 60
    email_code_length: int = 6
    smtp_host: str = ""
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_port: int = 465
    smtp_use_ssl: bool = True
    cors_allow_origins: str = ""
    cors_allow_credentials: bool = True

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
        # 支持 database.schema 复合写法；数据库名取第一段。
        if "." in database_path:
            database_name, _schema_name = database_path.split(".", 1)
            return database_name or "postgres"

        return database_path

    @property
    def postgres_schema(self) -> str | None:
        path = urlparse(_remove_jdbc_prefix(self.postgres_jdbc_url)).path.lstrip("/")
        database_path = path or "postgres"
        # 当未显式提供 schema 时返回 None，保持默认 search_path。
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

    @property
    def smtp_from_address(self) -> str:
        # 兼容空值或占位写法，统一回退到 SMTP_USERNAME 作为发件人。
        if not self.smtp_from:
            return self.smtp_username

        if self.smtp_from.startswith("${") and self.smtp_from.endswith("}"):
            return self.smtp_username

        return self.smtp_from

    @property
    def cors_allow_origins_list(self) -> list[str]:
        parsed_origins: list[str] = []
        seen_origins: set[str] = set()
        for raw_origin in self.cors_allow_origins.split(","):
            normalized_origin = raw_origin.strip()
            if not normalized_origin:
                continue
            if normalized_origin in seen_origins:
                continue

            seen_origins.add(normalized_origin)
            parsed_origins.append(normalized_origin)

        # 鉴权安全边界：允许凭证跨域时，禁止使用通配符，避免任意站点携带用户会话。
        if self.cors_allow_credentials and "*" in parsed_origins:
            raise ValueError(
                "Invalid CORS_ALLOW_ORIGINS: wildcard '*' is not allowed when CORS_ALLOW_CREDENTIALS=true"
            )

        return parsed_origins


@lru_cache
def get_settings() -> Settings:
    return Settings()
