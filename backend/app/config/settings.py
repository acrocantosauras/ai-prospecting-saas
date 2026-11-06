"""Application configuration from environment variables."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "AI Prospecting SaaS"
    app_version: str = "0.1.0"
    environment: str = "development"
    debug: bool = False
    frontend_url: str = "http://localhost:3000"

    # Demo mode
    demo_mode: bool = True
    demo_workspace_slug: str = "demo"

    # Database
    database_url: str = "sqlite:///./data/prospecting.db"
    database_dir: str = "./data"

    # AI providers
    ai_provider: str = "demo"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str = "https://api.openai.com/v1"

    # Google Sheets
    google_sheets_enabled: bool = False
    google_credentials_path: str = ""
    google_sheet_id: str = ""
    google_sheet_tab_name: str = "Leads"

    @property
    def is_google_sheets_configured(self) -> bool:
        return bool(
            self.google_sheets_enabled
            and self.google_credentials_path
            and self.google_sheet_id
        )


@lru_cache
def settings() -> Settings:
    return Settings()


settings_instance = settings()


def get_settings() -> Settings:
    return settings()
