"""Application configuration loaded from environment variables."""

from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # App
    app_name: str = "SpesaSmart API"
    debug: bool = False

    # Database (Supabase PostgreSQL)
    database_url: str = "postgresql+asyncpg://postgres:password@localhost:5432/spesasmart"
    supabase_url: str = ""
    supabase_key: str = ""

    # Google Cloud
    google_application_credentials: str = ""
    google_project_id: str = ""

    # Gemini AI
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"

    # Telegram Bot
    telegram_bot_token: str = ""

    # Scraping
    scraping_headless: bool = True
    scraping_timeout: int = 30000  # ms

    # Scheduler
    scheduler_enabled: bool = True

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }


@lru_cache
def get_settings() -> Settings:
    return Settings()
