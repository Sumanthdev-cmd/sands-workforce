from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-based application configuration."""

    app_name: str = "Workforce Management API"
    app_version: str = "0.1.0"
    environment: str = "development"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    cors_origins: str = (
        "http://localhost:5173,http://127.0.0.1:5173"
    )

    database_url: str
    redis_url: str

    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "workforce-management-api"
    jwt_audience: str = "workforce-management-clients"

    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    initial_organization_name: str = "Workforce Organization"
    initial_organization_code: str = "WORKFORCE"

    initial_admin_employee_code: str = "ADMIN001"
    initial_admin_email: str | None = None
    initial_admin_password: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def cors_origin_list(self) -> list[str]:
        """Return normalized, explicitly configured browser origins."""

        return [
            origin.strip().rstrip("/")
            for origin in self.cors_origins.split(",")
            if origin.strip()
        ]


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings."""

    return Settings()
