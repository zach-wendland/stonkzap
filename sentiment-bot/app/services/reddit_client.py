from typing import List
from datetime import datetime
from app.services.types import SocialPost
from app.config import get_settings

def search_reddit_bundle(inst: dict, since: datetime) -> List[SocialPost]:
    settings = get_settings()

    if not settings.reddit_client_id or not settings.reddit_client_secret:
        return []

    # TODO: Implement Reddit OAuth and search
    # - Get OAuth token
    # - Search relevant subreddits (wallstreetbets, stocks, investing)
    # - Search for cashtag and company name
    # - Fetch top-level posts and comments
    # - Map to SocialPost format

    return []
