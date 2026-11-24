from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parents[2]
WORKSPACE_DIR = ROOT_DIR


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=[str(WORKSPACE_DIR / ".env"), str(ROOT_DIR / ".env")],
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "YoursBuddy AI"
    api_v1_prefix: str = "/api/v1"
    environment: str = "development"

    # API & Database credentials (never expose via public APIs)
    openai_api_key: Optional[str] = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4o", alias="OPENAI_MODEL")
    gemini_api_key: Optional[str] = Field(default=None, alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-3.8-flash", alias="GEMINI_MODEL")
    tavily_api_key: Optional[str] = Field(default=None, alias="TAVILY_API_KEY")
    database_url: Optional[str] = Field(default=None, alias="DATABASE_URL")
    apollo_api_key: Optional[str] = Field(default=None, alias="APOLLO_API_KEY")

    # Service URLs
    backend_url: str = Field(default="http://localhost:8000", alias="BACKEND_URL")
    frontend_url: str = Field(default="http://localhost:3000", alias="FRONTEND_URL")

    # Browser settings
    browser_headless: bool = Field(default=False, alias="BROWSER_HEADLESS")
    browser_channel: str = Field(default="chrome", alias="BROWSER_CHANNEL")
    browser_user_data_dir: str = Field(
        default=str(WORKSPACE_DIR / "data" / "browser_profile"),
        alias="BROWSER_USER_DATA_DIR",
    )
    playwright_timeout_ms: int = Field(default=30000, alias="PLAYWRIGHT_TIMEOUT_MS")

    @property
    def resolved_browser_user_data_dir(self) -> Path:
        p = Path(self.browser_user_data_dir)
        if not p.is_absolute():
            return (WORKSPACE_DIR / p).resolve()
        return p.resolve()

    # Research defaults (configurable via Settings)
    default_search_keyword: str = Field(
        default="Real Estate Podcast", alias="DEFAULT_SEARCH_KEYWORD"
    )
    quality_threshold: int = Field(default=65, alias="QUALITY_THRESHOLD")
    max_posts_per_run: int = Field(default=10, alias="MAX_POSTS_PER_RUN")
    company_access_key: str = Field(
        default="YoursBuddy2026", alias="COMPANY_ACCESS_KEY"
    )

    # Optional n8n Cloud webhook integration
    n8n_webhook_url: Optional[str] = Field(default=None, alias="N8N_WEBHOOK_URL")

    # Local directories inside javis workspace
    data_dir: Path = WORKSPACE_DIR / "data"
    screenshots_dir: Path = WORKSPACE_DIR / "data" / "screenshots"
    exports_dir: Path = WORKSPACE_DIR / "exports"

    def ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)
        self.exports_dir.mkdir(parents=True, exist_ok=True)
        Path(self.browser_user_data_dir).mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_directories()
    return settings

