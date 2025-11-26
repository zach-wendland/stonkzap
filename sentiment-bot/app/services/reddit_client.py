from typing import List
from datetime import datetime
import praw
import logging
from app.services.types import SocialPost
from app.config import get_settings

logger = logging.getLogger(__name__)

# Subreddits to search for stock discussion
SUBREDDITS = ["wallstreetbets", "stocks", "investing", "stockmarket"]

def search_reddit_bundle(inst: dict, since: datetime) -> List[SocialPost]:
    """
    Search Reddit for posts and comments about a stock symbol.

    Args:
        inst: Instrument dict with 'symbol' and 'company_name' keys
        since: Only return posts created after this datetime

    Returns:
        List of SocialPost objects from Reddit
    """
    settings = get_settings()

    if not settings.reddit_client_id or not settings.reddit_client_secret:
        return []

    symbol = inst.get("symbol", "")
    company_name = inst.get("company_name", "")

    if not symbol and not company_name:
        return []

    posts = []
    since_timestamp = int(since.timestamp())

    try:
        # Initialize PRAW with app authentication
        reddit = praw.Reddit(
            client_id=settings.reddit_client_id,
            client_secret=settings.reddit_client_secret,
            user_agent=settings.reddit_user_agent,
        )

        # Search queries to try
        queries = [f"${symbol}"]
        if company_name:
            queries.append(company_name)

        for subreddit_name in SUBREDDITS:
            try:
                subreddit = reddit.subreddit(subreddit_name)

                for query in queries:
                    try:
                        # Search for posts matching the symbol or company name
                        for submission in subreddit.search(query, time_filter="day", limit=50):
                            try:
                                # Check if post is after our time window
                                if submission.created_utc < since_timestamp:
                                    continue

                                post = SocialPost(
                                    source="reddit",
                                    platform_id=submission.id,
                                    author_id=submission.author.id if submission.author else "deleted",
                                    author_handle=submission.author.name if submission.author else "[deleted]",
                                    created_at=datetime.fromtimestamp(submission.created_utc),
                                    text=submission.title + "\n" + submission.selftext,
                                    like_count=submission.ups,
                                    reply_count=submission.num_comments,
                                    follower_count=None,  # Reddit doesn't expose karma in API easily
                                    permalink=f"https://reddit.com{submission.permalink}",
                                    lang="en"
                                )
                                posts.append(post)

                                # Also fetch top comments for this submission
                                try:
                                    submission.comments.replace_more(limit=0)  # Avoid "MoreComments" objects
                                    for comment in submission.comments.list()[:20]:  # Top 20 comments
                                        if comment.created_utc < since_timestamp:
                                            continue

                                        comment_post = SocialPost(
                                            source="reddit",
                                            platform_id=comment.id,
                                            author_id=comment.author.id if comment.author else "deleted",
                                            author_handle=comment.author.name if comment.author else "[deleted]",
                                            created_at=datetime.fromtimestamp(comment.created_utc),
                                            text=comment.body,
                                            like_count=comment.ups,
                                            reply_count=None,
                                            follower_count=None,
                                            permalink=f"https://reddit.com{comment.permalink}",
                                            reply_to_id=submission.id,
                                            lang="en"
                                        )
                                        posts.append(comment_post)
                                except Exception as e:
                                    logger.warning(f"Failed to fetch comments for Reddit post {submission.id}: {e}")
                                    continue

                            except Exception as e:
                                logger.warning(f"Failed to process Reddit post: {e}")
                                continue

                    except Exception as e:
                        logger.warning(f"Failed to search subreddit {subreddit_name} for query '{query}': {e}")
                        continue

            except Exception as e:
                logger.warning(f"Failed to access subreddit {subreddit_name}: {e}")
                continue

    except Exception as e:
        logger.error(f"Failed to initialize Reddit API for symbol {symbol}: {e}")
        return []

    logger.info(f"Retrieved {len(posts)} posts/comments from Reddit for symbol {symbol}")
    return posts
