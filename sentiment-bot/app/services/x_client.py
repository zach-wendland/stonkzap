from typing import List, Dict, Any
from datetime import datetime
import httpx
import logging
from app.services.types import SocialPost
from app.config import get_settings

logger = logging.getLogger(__name__)

def search_x_bundle(inst: dict, since: datetime) -> List[SocialPost]:
    """
    Search X (Twitter) API v2 for posts about a stock symbol.

    Args:
        inst: Instrument dict with 'symbol' key
        since: Only return posts created after this datetime

    Returns:
        List of SocialPost objects from X/Twitter
    """
    settings = get_settings()

    if not settings.x_bearer_token:
        return []

    symbol = inst.get("symbol", "")
    if not symbol:
        return []

    posts = []

    # Build query: search for cashtag, English only, exclude retweets
    query = f"${symbol} (lang:en) -is:retweet"

    bearer_token = settings.x_bearer_token
    headers = {
        "Authorization": f"Bearer {bearer_token}",
        "User-Agent": "sentiment-bot/1.0"
    }

    next_token = None

    with httpx.Client() as client:
        while True:
            # Build request parameters
            params = {
                "query": query,
                "tweet.fields": "created_at,public_metrics,author_id,lang",
                "user.fields": "username,followers_count",
                "expansions": "author_id",
                "max_results": 100,
                "start_time": since.isoformat() + "Z",
            }

            if next_token:
                params["next_token"] = next_token

            try:
                response = client.get(
                    "https://api.twitter.com/2/tweets/search/recent",
                    headers=headers,
                    params=params,
                    timeout=10.0
                )

                # Handle rate limiting
                if response.status_code == 429:
                    logger.warning(f"X API rate limited for symbol {symbol}")
                    break

                response.raise_for_status()

                data = response.json()

                # No tweets found
                if "data" not in data:
                    break

                tweets = data.get("data", [])
                includes = data.get("includes", {})

                # Build user lookup map
                users_by_id = {u["id"]: u for u in includes.get("users", [])}

                # Map each tweet to SocialPost
                for tweet in tweets:
                    try:
                        tweet_id = tweet["id"]
                        text = tweet["text"]
                        created_at_str = tweet["created_at"]
                        metrics = tweet.get("public_metrics", {})
                        author_id = tweet.get("author_id", "")

                        # Parse ISO 8601 datetime
                        created_at = datetime.fromisoformat(
                            created_at_str.replace("Z", "+00:00")
                        )

                        user = users_by_id.get(author_id, {})
                        author_handle = user.get("username", f"user_{author_id}")
                        follower_count = user.get("followers_count")

                        post = SocialPost(
                            source="x",
                            platform_id=tweet_id,
                            author_id=author_id,
                            author_handle=author_handle,
                            created_at=created_at,
                            text=text,
                            like_count=metrics.get("like_count"),
                            reply_count=metrics.get("reply_count"),
                            repost_count=metrics.get("retweet_count"),
                            follower_count=follower_count,
                            permalink=f"https://twitter.com/{author_handle}/status/{tweet_id}",
                            lang="en"
                        )
                        posts.append(post)
                    except (KeyError, ValueError) as e:
                        logger.warning(f"Failed to parse tweet {tweet.get('id', 'unknown')}: {e}")
                        continue

                # Check for pagination
                meta = data.get("meta", {})
                next_token = meta.get("next_token")

                if not next_token:
                    break

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    logger.warning(f"X API rate limited for symbol {symbol}")
                    break
                else:
                    logger.error(f"X API error for symbol {symbol}: {e.response.status_code}")
                    break
            except Exception as e:
                logger.error(f"Error searching X API for symbol {symbol}: {e}")
                break

    logger.info(f"Retrieved {len(posts)} posts from X for symbol {symbol}")
    return posts
