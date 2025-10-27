from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    # API Keys
    x_bearer_token: str = ""
    reddit_client_id: str = ""
    reddit_client_secret: str = ""
    reddit_user_agent: str = "sentiment-bot/1.0"

    # Partners
    st_firestream_url: str = ""
    st_token: str = ""

    # Discord
    discord_bot_token: str = ""
    discord_guild_ids: str = ""
    discord_channel_allowlist: str = ""

    # Flags
    allow_unofficial: bool = False
    dry_run: bool = False

    # Logging
    log_level: str = "INFO"

    # Rate Limiting
    rate_limit_enabled: bool = True
    rate_limit_requests: int = 100
    rate_limit_window: int = 60  # seconds

    # Database
    database_url: str = "postgresql+psycopg://user:pass@localhost:5432/sentiment"
    redis_url: str = "redis://localhost:6379/0"

    class Config:
        env_file = ".env"
        case_sensitive = False

@lru_cache()
def get_settings():
    return Settings()
