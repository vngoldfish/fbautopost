"""
app/core/config.py
Application Settings with Pydantic and Environment Variable Support.
"""

import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="allow"
    )

    # Server Binding
    HOST: str = "0.0.0.0"
    PORT: int = 19823

    # Security Secrets
    # In development or if unset, empty string disables strict token enforcement
    SYNC_TOKEN: str = os.environ.get("SYNC_TOKEN", "")
    PROJECT_KEY_DEFAULT: str = "all"
    THEME_VER: int = 0x5A

    # Rate Limiting
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_POLL_PER_MIN: int = 60
    RATE_LIMIT_CREATION_PER_MIN: int = 120
    RATE_LIMIT_GENERAL_PER_MIN: int = 300

    # Paths
    BASE_DIR: str = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    DATA_DIR: str = os.path.join(BASE_DIR, "data")
    UPLOADS_DIR: str = os.path.join(BASE_DIR, "uploads")
    LOGS_DIR: str = os.path.join(BASE_DIR, "logs")
    DB_PATH: str = os.path.join(DATA_DIR, "fbauto.db")
    ADMIN_HTML_PATH: str = os.path.join(BASE_DIR, "admin.html")

    # Facebook API
    FB_GRAPH_API_URL: str = "https://graph.facebook.com/v19.0"

settings = Settings()
