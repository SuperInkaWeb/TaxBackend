from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import computed_field
from typing import Literal


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_NAME: str = "SIRE Bot"
    APP_ENV: Literal["development", "production"] = "development"

    MAX_CONCURRENT_JOBS: int = 3

    SUNAT_POLL_TIMEOUT_MINUTES: int = 90

    ENCRYPTION_KEY: str

    AUTH0_DOMAIN: str = ""
    AUTH0_AUDIENCE: str = ""
    AUTH0_SPA_CLIENT_ID: str = ""
    AUTH0_MGMT_CLIENT_ID: str = ""
    AUTH0_MGMT_CLIENT_SECRET: str = ""

    DATABASE_URL: str

    STORAGE_LOCAL_PATH: str = "./storage"

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
