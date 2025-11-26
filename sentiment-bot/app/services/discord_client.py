from typing import List, Set
from datetime import datetime
import httpx
import logging
from app.services.types import SocialPost
from app.config import get_settings

logger = logging.getLogger(__name__)

def collect_discord(inst: dict, since: datetime) -> List[SocialPost]:
    """
    Collect messages from Discord guilds and channels.

    Only reads from allowed guilds and channels via configuration.
    Uses Discord REST API (HTTP requests).

    Args:
        inst: Instrument dict (for reference)
        since: Only return messages created after this datetime

    Returns:
        List of SocialPost objects from Discord
    """
    settings = get_settings()

    if not settings.discord_bot_token:
        return []

    # Parse allowed guild and channel IDs from config
    guild_ids = _parse_ids(settings.discord_guild_ids)
    channel_allowlist = _parse_ids(settings.discord_channel_allowlist)

    if not guild_ids:
        logger.warning("No Discord guild IDs configured")
        return []

    posts = []
    bearer_token = settings.discord_bot_token
    headers = {
        "Authorization": f"Bot {bearer_token}",
        "User-Agent": "sentiment-bot/1.0"
    }

    with httpx.Client() as client:
        # For each allowed guild, fetch allowed channels
        for guild_id in guild_ids:
            try:
                # Get channels in guild
                channels_url = f"https://discord.com/api/v10/guilds/{guild_id}/channels"

                try:
                    channels_resp = client.get(
                        channels_url,
                        headers=headers,
                        timeout=10.0
                    )
                    channels_resp.raise_for_status()
                    channels = channels_resp.json()
                except httpx.HTTPStatusError as e:
                    logger.warning(f"Failed to fetch channels for guild {guild_id}: {e.response.status_code}")
                    continue

                # Filter to text channels in allowlist
                for channel in channels:
                    channel_id = str(channel.get("id"))
                    channel_type = channel.get("type")

                    # Type 0 = text channel
                    if channel_type != 0:
                        continue

                    # Check if channel is in allowlist
                    if channel_allowlist and channel_id not in channel_allowlist:
                        continue

                    # Fetch messages from this channel
                    try:
                        messages_url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
                        params = {
                            "limit": 100,
                        }

                        # Fetch up to 2 batches of messages (200 total)
                        for _ in range(2):
                            try:
                                msgs_resp = client.get(
                                    messages_url,
                                    headers=headers,
                                    params=params,
                                    timeout=10.0
                                )

                                if msgs_resp.status_code == 429:
                                    logger.warning(f"Discord API rate limited for channel {channel_id}")
                                    break

                                msgs_resp.raise_for_status()
                                messages = msgs_resp.json()

                                if not messages:
                                    break

                                # Process each message
                                for msg in messages:
                                    try:
                                        msg_id = msg.get("id")
                                        content = msg.get("content", "")
                                        created_at_str = msg.get("timestamp", "")
                                        author = msg.get("author", {})
                                        is_bot = author.get("bot", False)

                                        # Skip bot messages
                                        if is_bot:
                                            continue

                                        # Skip empty messages
                                        if not content:
                                            continue

                                        # Parse ISO 8601 datetime
                                        if created_at_str:
                                            created_at = datetime.fromisoformat(
                                                created_at_str.replace("Z", "+00:00")
                                            )
                                        else:
                                            created_at = datetime.utcnow()

                                        # Skip if older than window
                                        if created_at < since:
                                            # Messages are in descending order, so we can break here
                                            break

                                        author_id = author.get("id", "")
                                        author_handle = author.get("username", f"user_{author_id}")

                                        post = SocialPost(
                                            source="discord",
                                            platform_id=msg_id,
                                            author_id=author_id,
                                            author_handle=author_handle,
                                            created_at=created_at,
                                            text=content,
                                            like_count=None,
                                            follower_count=None,
                                            permalink=f"https://discord.com/channels/{guild_id}/{channel_id}/{msg_id}",
                                            lang="en"
                                        )
                                        posts.append(post)

                                    except (KeyError, ValueError) as e:
                                        logger.warning(f"Failed to parse Discord message: {e}")
                                        continue

                                # For pagination, use the last message ID
                                if messages:
                                    last_msg_id = messages[-1].get("id")
                                    params["before"] = last_msg_id

                            except httpx.HTTPStatusError as e:
                                if e.response.status_code == 429:
                                    logger.warning(f"Discord API rate limited")
                                else:
                                    logger.error(f"Discord API error for channel {channel_id}: {e.response.status_code}")
                                break
                            except Exception as e:
                                logger.error(f"Error fetching Discord messages for channel {channel_id}: {e}")
                                break

                    except Exception as e:
                        logger.error(f"Error processing channel {channel_id}: {e}")
                        continue

            except Exception as e:
                logger.error(f"Error processing guild {guild_id}: {e}")
                continue

    logger.info(f"Retrieved {len(posts)} messages from Discord")
    return posts


def _parse_ids(ids_str: str) -> Set[str]:
    """Parse comma-separated IDs from config string."""
    if not ids_str:
        return set()
    return {id.strip() for id in ids_str.split(",") if id.strip()}
