from typing import List
from datetime import datetime
from app.services.types import SocialPost
from app.config import get_settings

def search_x_bundle(inst: dict, since: datetime) -> List[SocialPost]:
    settings = get_settings()

    if not settings.x_bearer_token:
        return []

    # TODO: Implement X API v2 Recent Search
    # - Build query: f"${inst['symbol']} (lang:en) -is:retweet"
    # - Handle pagination (next_token)
    # - Implement rate limit backoff
    # - Map to SocialPost with public_metrics

    return []
