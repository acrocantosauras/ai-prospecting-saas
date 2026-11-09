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

    # Authentication and authorization.
    # Sessions are opaque server-side tokens delivered in an HttpOnly cookie;
    # nothing secret is derived from configuration, so no signing key is needed.
    auth_session_cookie: str = "prospect_session"
    auth_csrf_cookie: str = "prospect_csrf"
    auth_csrf_header: str = "X-CSRF-Token"
    auth_session_ttl_hours: int = 12
    auth_session_idle_minutes: int = 120
    auth_cookie_secure: bool = False  # forced on in production by the startup check
    auth_cookie_samesite: str = "lax"  # lax | strict | none
    auth_cookie_domain: str = ""
    auth_login_max_failures: int = 5
    auth_login_window_seconds: int = 900
    auth_max_active_sessions: int = 10
    # Optional development/production bootstrap. Empty by default: nothing is
    # seeded and no account exists until an operator opts in explicitly.
    auth_bootstrap_email: str = ""
    auth_bootstrap_password: str = ""
    auth_bootstrap_workspace_slug: str = "demo"
    auth_bootstrap_workspace_name: str = "Demo Workspace"

    # Database
    database_url: str = "sqlite:///./data/prospecting.db"
    database_dir: str = "./data"

    # AI providers
    ai_provider: str = "demo"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str = "https://api.openai.com/v1"

    # Prospecting engine provider selection.
    # "demo" keeps the deterministic synthetic provider; "real" requires a
    # configured search API for discovery/research. People and email-verification
    # integrations are not shipped, so "real" batches report those capabilities
    # as not_configured instead of fabricating data.
    prospecting_mode: str = "demo"
    search_provider: str = "tavily"  # tavily | serper
    tavily_api_key: str = ""
    serper_api_key: str = ""

    # Provider resilience
    provider_timeout_seconds: float = 15.0
    provider_max_attempts: int = 3
    provider_backoff_seconds: float = 0.5
    provider_max_backoff_seconds: float = 8.0
    provider_min_interval_seconds: float = 0.0

    # Qualification policy (customer-specific rules are configurable)
    qualification_min_decision_makers: int = 2
    qualification_min_sources: int = 1
    qualification_min_fit_confidence: float = 0.35
    qualification_min_research_confidence: float = 0.2
    qualification_require_verified_emails: bool = True
    qualification_excluded_industries: str = ""
    qualification_excluded_domains: str = ""
    qualification_excluded_name_keywords: str = ""
    qualification_allowed_countries: str = ""

    # Cost controls (usage is always measured, even when a provider is free)
    batch_cost_budget_usd: float = 2.0
    cost_search_call_usd: float = 0.008
    cost_llm_call_usd: float = 0.0
    cost_enrichment_lookup_usd: float = 0.0
    cost_email_verification_usd: float = 0.0
    discovery_oversample_factor: int = 3
    discovery_max_candidates: int = 300

    # Google Sheets
    google_sheets_enabled: bool = False
    google_credentials_path: str = ""
    google_sheet_id: str = ""
    google_sheet_tab_name: str = "Leads"

    @property
    def is_search_api_configured(self) -> bool:
        """Return True when a real search API key is available."""
        provider = (self.search_provider or "").lower()
        if provider == "tavily":
            return bool(self.tavily_api_key)
        if provider == "serper":
            return bool(self.serper_api_key)
        return False

    @property
    def is_llm_configured(self) -> bool:
        """Return True when a real LLM analysis provider is configured."""
        return self.ai_provider == "openai" and bool(self.openai_api_key)

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
