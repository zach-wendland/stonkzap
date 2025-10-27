from typing import List
from datetime import datetime
from app.services.types import SocialPost
from app.config import get_settings

def collect_discord(inst: dict, since: datetime) -> List[SocialPost]:
    settings = get_settings()

    if not settings.discord_bot_token:
        return []

    # TODO: Implement Discord Gateway client
    # - Only connect to guilds in DISCORD_GUILD_IDS
    # - Only read from channels in DISCORD_CHANNEL_ALLOWLIST
    # - Message Content intent must be enabled
    # - Extract cashtags from messages
    # - Never read DMs or non-allowlisted channels

    return []
