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
    discord_alerts_channel: str = ""  # Channel ID for trading alerts

    # Flags
    allow_unofficial: bool = False
    dry_run: bool = False

    # Authentication
    jwt_secret_key: str = "your-secret-key-change-in-production"  # Load from env
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7

    # Database
    database_url: str = "postgresql+psycopg://user:pass@localhost:5432/sentiment"
    redis_url: str = "redis://localhost:6379/0"

    class Config:
        env_file = ".env"
        case_sensitive = False

@lru_cache()
def get_settings():
    return Settings()
