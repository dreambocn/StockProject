from functools import lru_cache
from urllib.parse import quote, urlparse

from pydantic import model_validator
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
    redis_username: str = ""
    redis_password: str = ""
    jwt_secret_key: str = "change-this-secret-key-to-32-chars-min"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7
    postgres_maintenance_db: str = "postgres"
    db_auto_create_database: bool = True
    db_auto_create_tables: bool = True
    # 登录失败计数达到阈值后触发验证码挑战。
    login_captcha_threshold: int = 2
    login_fail_window_seconds: int = 900
    captcha_ttl_seconds: int = 300
    captcha_length: int = 4
    email_code_ttl_seconds: int = 300
    email_code_cooldown_seconds: int = 60
    email_code_length: int = 6
    email_code_ip_limit_per_minute: int = 10
    email_code_ip_limit_per_day: int = 200
    email_code_ip_block_seconds: int = 900
    # 是否信任代理头解析真实客户端 IP，开启前需限制可信代理来源。
    trust_proxy_headers: bool = False
    # 仅在信任代理头时生效，逗号分隔的可信代理 IP 列表。
    trusted_proxy_ips: str = ""
    smtp_host: str = ""
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_port: int = 465
    smtp_use_ssl: bool = True
    cors_allow_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    cors_allow_credentials: bool = True
    cors_allow_origin_regex: str = r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"
    tushare_token: str = ""
    stock_sync_trade_days: int = 120
    stock_daily_cache_ttl_seconds: int = 600
    stock_trade_cal_cache_ttl_seconds: int = 86400
    stock_adj_factor_cache_ttl_seconds: int = 3600
    stock_related_news_cache_ttl_seconds: int = 3600
    hot_news_cache_ttl_seconds: int = 3600
    policy_news_cache_ttl_seconds: int = 1800
    news_cache_version_legacy_fallback_enabled: bool = True
    news_cache_version_legacy_fallback_seconds: int = 3600
    candidate_hot_search_cache_ttl_seconds: int = 3600
    candidate_research_report_cache_ttl_seconds: int = 43200
    candidate_research_refresh_interval_hours: int = 12
    llm_base_url: str = "https://aixj.vip"
    llm_wire_api: str = "responses"
    llm_api_key: str = ""
    llm_model: str = "gpt-5.1-codex-mini"
    llm_reasoning_effort: str = "high"
    llm_stream_enabled: bool = True
    llm_web_search_enabled: bool = False
    web_source_metadata_timeout_seconds: int = 3
    web_source_metadata_cache_ttl_seconds: int = 86400
    web_source_metadata_failure_ttl_seconds: int = 7200
    web_source_metadata_max_bytes: int = 524288
    analysis_active_session_ttl_seconds: int = 300
    analysis_report_freshness_minutes: int = 60
    analysis_worker_poll_interval_seconds: int = 5
    analysis_running_stale_seconds: int = 900
    analysis_generation_event_limit: int = 30
    analysis_generation_candidate_pool_multiplier: int = 4
    analysis_generation_stock_quota: int = 12
    analysis_generation_policy_quota: int = 8
    analysis_generation_hot_quota: int = 10
    analysis_summary_event_limit: int = 20
    analysis_summary_candidate_pool_multiplier: int = 4
    init_admin_username: str = ""
    init_admin_email: str = ""
    init_admin_password: str = ""

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
        parsed_url = urlparse(_remove_jdbc_prefix(self.redis_jdbc_url))
        resolved_username = self.redis_username or (parsed_url.username or "")
        resolved_password = self.redis_password or (parsed_url.password or "")

        # 鉴权安全边界：优先使用独立环境变量，避免把明文凭据硬编码在 REDIS_JDBC_URL。
        # 同时对用户名和密码做 URL 编码，防止特殊字符导致连接串解析歧义。
        if resolved_username and resolved_password:
            username = quote(resolved_username, safe="")
            password = quote(resolved_password, safe="")
            auth_segment = f"{username}:{password}@"
        elif resolved_password:
            password = quote(resolved_password, safe="")
            auth_segment = f":{password}@"
        else:
            auth_segment = ""

        return (
            f"redis://{auth_segment}{self.redis_host}:{self.redis_port}/{self.redis_db}"
        )

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

    @property
    def trusted_proxy_ips_list(self) -> list[str]:
        parsed_proxies: list[str] = []
        seen_proxies: set[str] = set()
        for raw_proxy in self.trusted_proxy_ips.split(","):
            normalized_proxy = raw_proxy.strip()
            if not normalized_proxy:
                continue
            if normalized_proxy in seen_proxies:
                continue

            seen_proxies.add(normalized_proxy)
            parsed_proxies.append(normalized_proxy)

        return parsed_proxies

    @model_validator(mode="after")
    def validate_analysis_event_quotas(self) -> "Settings":
        quota_sum = (
            self.analysis_generation_stock_quota
            + self.analysis_generation_policy_quota
            + self.analysis_generation_hot_quota
        )
        if quota_sum > self.analysis_generation_event_limit:
            raise ValueError(
                "ANALYSIS_GENERATION_STOCK_QUOTA + ANALYSIS_GENERATION_POLICY_QUOTA + "
                "ANALYSIS_GENERATION_HOT_QUOTA 不能大于 ANALYSIS_GENERATION_EVENT_LIMIT"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
