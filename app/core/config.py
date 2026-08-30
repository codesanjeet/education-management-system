from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):

    # =========================
    # Security
    # =========================
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 12

    # =========================
    # Google OAuth
    # =========================
    GOOGLE_CLIENT_ID: str
    GOOGLE_CLIENT_SECRET: str

    # =========================
    # OpenAI
    # =========================
    OPENAI_API_KEY: str

    # =========================
    # Cloudflare R2
    # =========================
    R2_ACCESS_KEY: str
    R2_SECRET_KEY: str
    R2_ENDPOINT: str
    R2_PUBLIC_BASE_URL: str

    R2_PRIVATE_BUCKET_NAME: str
    R2_PUBLIC_BUCKET_NAME: str

    # =========================
    # Email
    # =========================
    RESEND_API_KEY: str
    EMAIL_FROM_ADDRESS: str

    # =========================
    # Notification
    # =========================
    NOTIFICATION_EMAIL_TOKEN_SECRET: str

    # =========================
    # Database
    # =========================
    DATABASE_URL: str

    # =========================
    # Application URLs
    # =========================
    BACKEND_BASE_URL: str
    FRONTEND_BASE_URL: str

    # =========================
    # CORS
    # =========================
    BACKEND_CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:8000",
    ]

    # =========================
    # Environment
    # =========================
    ENVIRONMENT: str = "development"

    # =========================
    # Pydantic Settings Config
    # =========================
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()