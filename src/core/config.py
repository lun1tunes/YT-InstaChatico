import os
from typing import Self
from pydantic import BaseModel, Field, model_validator, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict, EnvSettingsSource
from dotenv import load_dotenv

load_dotenv()


class DbSettings(BaseModel):
    url: str = Field(default_factory=lambda: os.getenv("DATABASE_URL", "").strip())
    echo: bool = Field(default=False)
    # echo: bool = True

    @model_validator(mode="after")
    def _validate(self) -> Self:
        if not self.url:
            raise ValueError("DATABASE_URL environment variable must be set.")
        return self


class CelerySettings(BaseModel):
    broker_url: str = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
    result_backend: str = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")


class OpenAISettings(BaseModel):
    api_key: str = Field(default_factory=lambda: os.getenv("OPENAI_API_KEY", "").strip())
    model_comment_classification: str = os.getenv("OPENAI_MODEL_CLASSIFICATION", "gpt-5-nano")
    model_comment_response: str = os.getenv("OPENAI_MODEL_RESPONSE", "gpt-5-mini")
    rpm_limit: int = int(os.getenv("OPENAI_RPM_LIMIT", "50"))
    tpm_limit: int = int(os.getenv("OPENAI_TPM_LIMIT", "100000"))

    @model_validator(mode="after")
    def _validate(self) -> Self:
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY environment variable must be set.")
        return self


class EmbeddingSettings(BaseModel):
    """Settings for vector embedding search"""

    # Понижен порог для русскоязычного контента (0.45 вместо 0.7)
    # text-embedding-3-small даёт более низкие similarity для русского языка
    similarity_threshold: float = float(os.getenv("EMBEDDING_SIMILARITY_THRESHOLD", "0.45"))
    model: str = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
    dimensions: int = int(os.getenv("EMBEDDING_DIMENSIONS", "1536"))


class InstagramSettings(BaseModel):
    access_token: str = Field(default_factory=lambda: os.getenv("INSTA_TOKEN", "").strip())
    api_version: str = os.getenv("INSTAGRAM_API_VERSION", "v23.0")
    base_url: str = f"https://graph.instagram.com/{os.getenv('INSTAGRAM_API_VERSION', 'v23.0')}"
    bot_username: str = os.getenv("INSTAGRAM_BOT_USERNAME", "")
    base_account_id: str = os.getenv("INSTAGRAM_BASE_ACC_ID", os.getenv("INSTAGRAM_BASE_ACCOUNT_ID", "")).strip()
    app_id: str = os.getenv("INSTAGRAM_APP_ID", "")
    app_secret: str = os.getenv("INSTAGRAM_APP_SECRET", "")
    app_access_token: str = os.getenv("INSTAGRAM_APP_ACCESS_TOKEN", "")
    rate_limit_redis_url: str = os.getenv(
        "INSTAGRAM_RATE_LIMIT_REDIS_URL",
        os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"),
    )
    replies_rate_limit_per_hour: int = int(os.getenv("INSTAGRAM_REPLIES_RATE_LIMIT_PER_HOUR", "750"))
    replies_rate_period_seconds: int = int(os.getenv("INSTAGRAM_REPLIES_RATE_PERIOD_SECONDS", "3600"))

    @model_validator(mode="after")
    def _validate(self) -> Self:
        if not self.access_token:
            raise ValueError("INSTA_TOKEN environment variable must be set.")
        return self


class TelegramSettings(BaseModel):
    bot_token: str = Field(default_factory=lambda: os.getenv("TG_TOKEN", "").strip())
    chat_id: str = Field(default_factory=lambda: os.getenv("TG_CHAT_ID", "").strip())
    tg_chat_alerts_thread_id: str = os.getenv("TG_CHAT_ALERTS_THREAD_ID", "")
    tg_chat_logs_thread_id: str = os.getenv("TG_CHAT_LOGS_THREAD_ID", "")

    @model_validator(mode="after")
    def _validate(self) -> Self:
        missing = []
        if not self.bot_token:
            missing.append("TG_TOKEN")
        if not self.chat_id:
            missing.append("TG_CHAT_ID")
        if missing:
            raise ValueError(f"Telegram configuration missing required environment variables: {', '.join(missing)}.")
        return self


class HealthSettings(BaseModel):
    cpu_warn_pct: int = int(os.getenv("HEALTH_CPU_WARN_PCT", "85"))
    mem_warn_pct: int = int(os.getenv("HEALTH_MEM_WARN_PCT", "85"))
    disk_warn_pct: int = int(os.getenv("HEALTH_DISK_WARN_PCT", "90"))
    check_interval_seconds: int = int(os.getenv("HEALTH_CHECK_INTERVAL_SECONDS", str(60 * 60)))
    mem_min_available_mb: int = int(os.getenv("HEALTH_MEM_MIN_AVAILABLE_MB", "512"))
    disk_min_free_gb: int = int(os.getenv("HEALTH_DISK_MIN_FREE_GB", "2"))
    disk_path: str = os.getenv("HEALTH_DISK_PATH", "/")


class DocsSettings(BaseModel):
    username: str = os.getenv("DOCS_USERNAME", "")
    password: str = os.getenv("DOCS_PASSWORD", "")


class JsonApiSettings(BaseModel):
    secret_key: str = Field(default_factory=lambda: os.getenv("JWT_SECRET_KEY", "").strip())
    algorithm: str = Field(default_factory=lambda: os.getenv("JWT_ALGORITHM", "HS256").strip() or "HS256")
    expire_minutes: int = Field(default_factory=lambda: int(os.getenv("JWT_EXPIRE_MINUTES", "1440")))

    @model_validator(mode="after")
    def _validate(self) -> Self:
        if not self.secret_key:
            raise ValueError("JWT_SECRET_KEY environment variable must be set.")
        if not self.algorithm:
            raise ValueError("JWT_ALGORITHM environment variable must be set.")
        if self.expire_minutes <= 0:
            raise ValueError("JWT_EXPIRE_MINUTES must be greater than zero.")
        return self


class MediaProxySettings(BaseModel):
    allowed_host_suffixes: list[str] = Field(
        default_factory=lambda: [
            "cdninstagram.com",
            "fbcdn.net",
            "instagramcdn.com",
            "akamaihd.net",
        ]
    )
    request_timeout_seconds: float = Field(default_factory=lambda: float(os.getenv("MEDIA_PROXY_TIMEOUT_SECONDS", "20")))

    @field_validator("allowed_host_suffixes", mode="before")
    @classmethod
    def _parse_allowed_hosts(cls, value):
        default_factory = cls.model_fields["allowed_host_suffixes"].default_factory
        default_value = default_factory() if callable(default_factory) else [
            "cdninstagram.com",
            "fbcdn.net",
            "instagramcdn.com",
            "akamaihd.net",
        ]
        if value is None:
            return default_value
        if isinstance(value, str):
            stripped = [item.strip().lower() for item in value.split(",") if item.strip()]
            return stripped or default_value
        if isinstance(value, (list, tuple, set)):
            stripped = [str(item).strip().lower() for item in value if str(item).strip()]
            return stripped or default_value
        raise ValueError("Invalid MEDIA_PROXY_ALLOWED_HOST_SUFFIXES format; provide comma-separated string or list.")


class S3Settings(BaseSettings):
    """S3 storage settings for SelectCloud."""

    model_config = SettingsConfigDict(extra="ignore")

    aws_access_key_id: str = Field(default_factory=lambda: os.getenv("AWS_ACCESS_KEY_ID", "").strip())
    aws_secret_access_key: str = Field(default_factory=lambda: os.getenv("AWS_SECRET_ACCESS_KEY", "").strip())
    bucket_name: str = Field(default_factory=lambda: os.getenv("BUCKET_NAME", "").strip())
    s3_url: str = Field(default_factory=lambda: os.getenv("S3_URL", "s3.ru-7.storage.selcloud.ru").strip())
    region: str = Field(default_factory=lambda: os.getenv("AWS_REGION", "ru-7").strip())

    @model_validator(mode="after")
    def _validate(self) -> Self:
        missing = [
            name for name, value in [
                ("AWS_ACCESS_KEY_ID", self.aws_access_key_id),
                ("AWS_SECRET_ACCESS_KEY", self.aws_secret_access_key),
                ("BUCKET_NAME", self.bucket_name),
            ] if not value
        ]
        if missing:
            raise ValueError(f"S3 configuration missing required environment variables: {', '.join(missing)}.")
        return self


class RelaxedEnvSettingsSource(EnvSettingsSource):
    def decode_complex_value(self, field_name, field, value):
        try:
            return super().decode_complex_value(field_name, field, value)
        except Exception:
            return value


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")
    api_v1_prefix: str = "/api/v1"
    app_secret: str = Field(default_factory=lambda: os.getenv("APP_SECRET", "").strip())
    app_webhook_verify_token: str = Field(default_factory=lambda: os.getenv("TOKEN", "").strip())
    cors_allowed_origins: list[str] = Field(default_factory=lambda: ["*"])
    cors_allow_credentials: bool = Field(default=False)
    db: DbSettings = DbSettings()
    celery: CelerySettings = CelerySettings()
    openai: OpenAISettings = OpenAISettings()
    embedding: EmbeddingSettings = EmbeddingSettings()
    instagram: InstagramSettings = InstagramSettings()
    telegram: TelegramSettings = TelegramSettings()
    health: HealthSettings = HealthSettings()
    docs: DocsSettings = DocsSettings()
    json_api: JsonApiSettings = JsonApiSettings()
    s3: S3Settings = S3Settings()
    media_proxy: MediaProxySettings = MediaProxySettings()

    @model_validator(mode="after")
    def _validate(self) -> Self:
        if not self.app_secret:
            raise ValueError("APP_SECRET environment variable must be set.")
        if not self.app_webhook_verify_token:
            raise ValueError("TOKEN environment variable (used as webhook verify token) must be set.")
        return self

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def _parse_cors_origins(cls, value):
        if value is None:
            return ["*"]
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return ["*"]
            if stripped == "*":
                return ["*"]
            return [item.strip() for item in stripped.split(",") if item.strip()]
        if isinstance(value, (list, tuple, set)):
            origins = [str(item).strip() for item in value if str(item).strip()]
            return origins or ["*"]
        raise ValueError("Invalid cors_allowed_origins format; provide comma-separated string or list.")

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        return (
            init_settings,
            RelaxedEnvSettingsSource(settings_cls),
            dotenv_settings,
            file_secret_settings,
        )


settings = Settings()
