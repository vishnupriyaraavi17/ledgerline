import os
from pathlib import Path
from typing import List, Union, Optional
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Determine project root (.env location)
ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
ENV_FILE_PATH = ROOT_DIR / ".env"


class Settings(BaseSettings):
    # Application Info
    PROJECT_NAME: str = "LedgerLine"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    VERSION: str = "0.2.0"

    # API Routing
    API_V1_STR: str = "/api/v1"
    BACKEND_HOST: str = "127.0.0.1"
    BACKEND_PORT: int = 8000

    # CORS
    BACKEND_CORS_ORIGINS: Union[List[str], str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",") if i.strip()]
        elif isinstance(v, (list, str)):
            return v
        raise ValueError(v)

    # Database Configuration (Application Runtime Role)
    POSTGRES_SERVER: str = "127.0.0.1"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "ledgerline_app"
    POSTGRES_PASSWORD: str = ""
    POSTGRES_DB: str = "ledgerline"

    # Schema Migration Owner Role Configuration
    MIGRATION_POSTGRES_USER: str = "ledgerline_owner"
    MIGRATION_POSTGRES_PASSWORD: Optional[str] = None

    # Redis Configuration (Distributed Rate Limiting & Caching)
    REDIS_URL: str = "redis://127.0.0.1:6379/0"

    # Authentication & JWT Configuration
    # Strict enforcement: Loaded strictly from environment with no default. Fails startup if missing or weak (<32 chars).
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    REFRESH_COOKIE_NAME: str = "ledgerline_refresh_token"

    @field_validator("JWT_SECRET_KEY")
    @classmethod
    def validate_jwt_secret_key(cls, v: str) -> str:
        if not v or len(v.strip()) < 32:
            raise ValueError(
                "JWT_SECRET_KEY must be provided via environment variables with at least 32 characters."
            )
        return v.strip()

    # Optional local development seed passwords (ignored in production)
    SEED_ADMIN_PASSWORD: Optional[str] = None
    SEED_HOLDER_PASSWORD: Optional[str] = None
    SEED_AUDITOR_PASSWORD: Optional[str] = None

    @property
    def RUNTIME_POSTGRES_USER(self) -> str:
        """Canonical fixed runtime role identifier."""
        from sqlalchemy.engine.url import make_url
        uri_user = make_url(self.SQLALCHEMY_DATABASE_URI).username
        if uri_user != "ledgerline_app":
            raise ValueError(
                f"SQLALCHEMY_DATABASE_URI username must be 'ledgerline_app', got '{uri_user}'"
            )
        if self.POSTGRES_USER != "ledgerline_app":
            raise ValueError(
                f"POSTGRES_USER must be 'ledgerline_app', got '{self.POSTGRES_USER}'"
            )
        return "ledgerline_app"

    @property
    def SQLALCHEMY_DATABASE_URI(self) -> str:
        return (
            f"postgresql+psycopg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@"
            f"{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def MIGRATION_DATABASE_URI(self) -> str:
        """Constructs migration connection URI using fixed ledgerline_owner role. Fails closed."""
        from sqlalchemy.engine.url import make_url
        if not self.MIGRATION_POSTGRES_PASSWORD:
            raise ValueError(
                "MIGRATION_DATABASE_URI is not configured. Migrations cannot execute under the application runtime role."
            )
        if self.MIGRATION_POSTGRES_USER != "ledgerline_owner":
            raise ValueError(
                f"MIGRATION_POSTGRES_USER must be 'ledgerline_owner', got '{self.MIGRATION_POSTGRES_USER}'"
            )
        uri = (
            f"postgresql+psycopg://{self.MIGRATION_POSTGRES_USER}:{self.MIGRATION_POSTGRES_PASSWORD}@"
            f"{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )
        parsed_user = make_url(uri).username
        if parsed_user != "ledgerline_owner":
            raise ValueError(
                f"MIGRATION_DATABASE_URI username must be 'ledgerline_owner', got '{parsed_user}'"
            )
        return uri

    @property
    def safe_db_info(self) -> str:
        """Returns non-sensitive database connection details for logging/diagnostics."""
        return f"{self.POSTGRES_USER}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    @property
    def safe_redis_info(self) -> str:
        """Returns non-sensitive Redis connection details for diagnostics (never exposes passwords)."""
        from urllib.parse import urlparse
        try:
            parsed = urlparse(self.REDIS_URL)
            host = parsed.hostname or "127.0.0.1"
            port = parsed.port or 6379
            db = parsed.path.lstrip("/") or "0"
            return f"{host}:{port}/{db}"
        except Exception:
            return "redis://***"

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE_PATH) if ENV_FILE_PATH.exists() else ".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
