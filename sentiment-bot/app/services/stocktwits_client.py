from typing import List
from datetime import datetime
from app.services.types import SocialPost
from app.config import get_settings

def collect_stocktwits(inst: dict, since: datetime) -> List[SocialPost]:
    settings = get_settings()

    if settings.st_firestream_url and settings.st_token:
        # TODO: Implement Firestream SSE connection
        pass

    # TODO: Fallback to allowed REST endpoints if available
    # Note: StockTwits has rate limits on public API

    return []
