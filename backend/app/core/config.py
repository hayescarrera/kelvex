from pydantic import model_validator
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # App
    APP_NAME: str = "ColdGrid"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    LOG_LEVEL: str = "INFO"

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://coldgrid:coldgrid_dev@db:5432/coldgrid"
    # Sync URL for Alembic migrations
    DATABASE_URL_SYNC: str = "postgresql://coldgrid:coldgrid_dev@db:5432/coldgrid"

    # Redis
    REDIS_URL: str = "redis://redis:6379/0"
    AUTH_RATE_LIMIT_PER_MINUTE: int = 30
    API_RATE_LIMIT_PER_MINUTE: int = 100

    # Auth
    SECRET_KEY: str = "dev-secret-key-change-in-production"
    CREDENTIAL_ENCRYPTION_KEY: str = ""
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    ALGORITHM: str = "HS256"

    # Registration gate — set REGISTRATION_OPEN=false + INVITE_SECRET in production
    REGISTRATION_OPEN: bool = True
    INVITE_SECRET: str = ""

    # OpenEI
    OPENEI_API_KEY: str = ""
    OPENEI_BASE_URL: str = "https://api.openei.org/utility_rates"

    # CORS
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"
    ALLOW_CREDENTIALS: bool = True

    # Error monitoring (optional)
    SENTRY_DSN: str = ""
    SENTRY_TRACES_SAMPLE_RATE: float = 0.0

    # Notifications
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = "alerts@coldgrid.io"
    SMTP_TLS: bool = True

    # SMS (Twilio)
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_FROM_NUMBER: str = ""  # e.g. "+15551234567"

    # Health checks
    HEALTHCHECK_STRICT: bool = False

    # File uploads
    MAX_UPLOAD_SIZE_MB: int = 50

    class Config:
        env_file = ".env"
        case_sensitive = True

    @model_validator(mode="after")
    def validate_production_security(self):
        environment = self.ENVIRONMENT.lower()
        is_production = environment in {"prod", "production"}

        if is_production and self.DEBUG:
            raise ValueError("DEBUG must be false in production")

        if is_production and self.SECRET_KEY == "dev-secret-key-change-in-production":
            raise ValueError("SECRET_KEY must be set to a strong value in production")

        if is_production and not self.CREDENTIAL_ENCRYPTION_KEY:
            raise ValueError("CREDENTIAL_ENCRYPTION_KEY is required in production")

        return self


@lru_cache()
def get_settings() -> Settings:
    return Settings()
