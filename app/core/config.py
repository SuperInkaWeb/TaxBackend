from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import computed_field
from typing import Literal


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_NAME: str = "SIRE Bot"
    APP_ENV: Literal["development", "production"] = "development"
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_HOURS: int = 8

    # Jobs de conciliación pesados (pico ~10GB RAM c/u). 1 = serializado.
    # Subir solo si el servidor tiene RAM para N picos simultáneos.
    MAX_CONCURRENT_JOBS: int = 1

    ENCRYPTION_KEY: str

    DATABASE_URL: str

    STORAGE_BACKEND: Literal["local", "r2"] = "local"
    STORAGE_LOCAL_PATH: str = "./storage"
    R2_ACCOUNT_ID: str = ""
    R2_ACCESS_KEY_ID: str = ""
    R2_SECRET_ACCESS_KEY: str = ""
    R2_BUCKET_NAME: str = "sire-reportes"

    RESEND_API_KEY: str = ""
    EMAIL_FROM: str = "noreply@example.com"

    CORS_ORIGINS: str = "http://localhost:5173"

    @computed_field
    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",")]

    @computed_field
    @property
    def is_development(self) -> bool:
        return self.APP_ENV == "development"


settings = Settings()
