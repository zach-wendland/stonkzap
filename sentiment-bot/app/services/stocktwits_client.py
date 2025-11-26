from typing import List, Optional
from datetime import datetime
import httpx
import logging
from app.services.types import SocialPost
from app.config import get_settings

logger = logging.getLogger(__name__)

def collect_stocktwits(inst: dict, since: datetime) -> List[SocialPost]:
    """
    Collect posts from StockTwits for a stock symbol.

    Uses public REST API endpoint (no authentication required).
    Firestream SSE is reserved for premium subscribers.

    Args:
        inst: Instrument dict with 'symbol' key
        since: Only return posts created after this datetime

    Returns:
        List of SocialPost objects from StockTwits
    """
    symbol = inst.get("symbol", "")
    if not symbol:
        return []

    posts = []

    try:
        with httpx.Client() as client:
            # StockTwits public API endpoint
            url = f"https://api.stocktwits.com/api/v2/streams/symbols/{symbol.lower()}/messages"

            # Max limit is 30 per request
            params = {
                "limit": 30,
                "filter": "all",  # Get all sentiment types
            }

            # Pagination: fetch multiple pages
            max_pages = 3
            current_page = 0

            while current_page < max_pages:
                try:
                    response = client.get(
                        url,
                        params=params,
                        timeout=10.0,
                        headers={"User-Agent": "sentiment-bot/1.0"}
                    )

                    # Handle rate limiting
                    if response.status_code == 429:
                        logger.warning(f"StockTwits rate limited for symbol {symbol}")
                        break

                    response.raise_for_status()

                    data = response.json()

                    # No messages found or error response
                    if data.get("status") == "error" or not data.get("messages"):
                        break

                    messages = data.get("messages", [])

                    # Process each message
                    for msg in messages:
                        try:
                            msg_id = msg.get("id")
                            body = msg.get("body", "")
                            created_at_str = msg.get("created_at", "")
                            user = msg.get("user", {})
                            sentiment = msg.get("sentiment", None)

                            # Parse ISO 8601 datetime
                            if created_at_str:
                                created_at = datetime.fromisoformat(
                                    created_at_str.replace("Z", "+00:00")
                                )
                            else:
                                created_at = datetime.utcnow()

                            # Skip if older than our window
                            if created_at < since:
                                continue

                            author_id = str(user.get("id", ""))
                            author_handle = user.get("username", f"user_{author_id}")
                            follower_count = user.get("followers", None)

                            # StockTwits stores sentiment as bullish/bearish;
                            # include in text for NLP processing
                            text_with_sentiment = body
                            if sentiment:
                                text_with_sentiment = f"[{sentiment.upper()}] {body}"

                            post = SocialPost(
                                source="stocktwits",
                                platform_id=str(msg_id),
                                author_id=author_id,
                                author_handle=author_handle,
                                created_at=created_at,
                                text=text_with_sentiment,
                                like_count=msg.get("likes", 0),
                                follower_count=follower_count,
                                permalink=f"https://stocktwits.com/symbol/{symbol.upper()}/message/{msg_id}",
                                lang="en"
                            )
                            posts.append(post)

                        except (KeyError, ValueError) as e:
                            logger.warning(f"Failed to parse StockTwits message {msg.get('id', 'unknown')}: {e}")
                            continue

                    # Check if there are more pages
                    links = data.get("links", {})
                    next_url = links.get("next")

                    if not next_url:
                        break

                    # Extract cursor for pagination
                    if "cursor=" in next_url:
                        cursor = next_url.split("cursor=")[-1]
                        params["cursor"] = cursor
                        current_page += 1
                    else:
                        break

                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 429:
                        logger.warning(f"StockTwits rate limited for symbol {symbol}")
                    else:
                        logger.error(f"StockTwits API error for symbol {symbol}: {e.response.status_code}")
                    break
                except Exception as e:
                    logger.error(f"Error fetching StockTwits data for symbol {symbol}: {e}")
                    break

    except Exception as e:
        logger.error(f"Failed to collect StockTwits posts for symbol {symbol}: {e}")
        return []

    logger.info(f"Retrieved {len(posts)} posts from StockTwits for symbol {symbol}")
    return posts
