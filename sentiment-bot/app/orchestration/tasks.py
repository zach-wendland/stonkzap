import datetime as dt
import logging
from typing import Dict, List
from app.services.resolver import resolve
from app.services.reddit_client import search_reddit_bundle
from app.services.x_client import search_x_bundle
from app.services.stocktwits_client import collect_stocktwits
from app.services.discord_client import collect_discord
from app.nlp.clean import normalize_post, extract_symbols
from app.nlp.sentiment import score_text
from app.nlp.embeddings import compute_embedding
from app.nlp.bot_filter import is_probable_bot
from app.storage.db import DB
from app.services.types import SocialPost

logger = logging.getLogger(__name__)

def healthcheck() -> Dict:
    """Health check with timestamp."""
    try:
        return {
            "status": "ok",
            "timestamp": dt.datetime.utcnow().isoformat(),
            "version": "1.0.0"
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "error",
            "timestamp": dt.datetime.utcnow().isoformat(),
            "error": str(e)
        }

def aggregate_social(symbol: str, window: str = "24h") -> Dict:
    """
    Complete pipeline: resolve symbol → collect posts → clean → score → aggregate.

    Args:
        symbol: Stock symbol to analyze
        window: Time window for analysis (e.g., "24h", "7d")

    Returns:
        Dictionary with aggregated sentiment results

    Raises:
        ValueError: If symbol cannot be resolved
    """
    logger.info(f"Starting sentiment aggregation for symbol={symbol}, window={window}")

    # Resolve symbol
    try:
        inst = resolve(symbol)
        inst_dict = inst.model_dump()
        logger.debug(f"Resolved {symbol} to {inst.company_name}")
    except Exception as e:
        logger.error(f"Failed to resolve symbol {symbol}: {e}")
        raise ValueError(f"Could not resolve symbol: {symbol}")

    # Parse time window
    try:
        since = dt.datetime.utcnow() - _parse_window(window)
        logger.debug(f"Analyzing posts since {since.isoformat()}")
    except Exception as e:
        logger.error(f"Failed to parse window {window}: {e}")
        raise ValueError(f"Invalid time window: {window}")

    # Collect from all sources
    posts: List[SocialPost] = []
    sources_status = {}

    # X/Twitter
    try:
        x_posts = search_x_bundle(inst_dict, since)
        posts.extend(x_posts)
        sources_status["x"] = len(x_posts)
        logger.info(f"Collected {len(x_posts)} posts from X")
    except Exception as e:
        logger.warning(f"Failed to collect from X: {e}")
        sources_status["x"] = 0

    # Reddit
    try:
        reddit_posts = search_reddit_bundle(inst_dict, since)
        posts.extend(reddit_posts)
        sources_status["reddit"] = len(reddit_posts)
        logger.info(f"Collected {len(reddit_posts)} posts from Reddit")
    except Exception as e:
        logger.warning(f"Failed to collect from Reddit: {e}")
        sources_status["reddit"] = 0

    # StockTwits
    try:
        st_posts = collect_stocktwits(inst_dict, since)
        posts.extend(st_posts)
        sources_status["stocktwits"] = len(st_posts)
        logger.info(f"Collected {len(st_posts)} posts from StockTwits")
    except Exception as e:
        logger.warning(f"Failed to collect from StockTwits: {e}")
        sources_status["stocktwits"] = 0

    # Discord
    try:
        discord_posts = collect_discord(inst_dict, since)
        posts.extend(discord_posts)
        sources_status["discord"] = len(discord_posts)
        logger.info(f"Collected {len(discord_posts)} posts from Discord")
    except Exception as e:
        logger.warning(f"Failed to collect from Discord: {e}")
        sources_status["discord"] = 0

    logger.info(f"Total posts collected: {len(posts)}")

    if not posts:
        logger.warning(f"No posts found for {symbol}")
        return {
            "symbol": symbol,
            "posts_found": 0,
            "posts_processed": 0,
            "sources": sources_status,
            "resolved_instrument": inst_dict,
            "error": "No posts found for this symbol"
        }

    # Clean and filter
    clean_posts = []
    filter_stats = {
        "total_input": len(posts),
        "no_symbols": 0,
        "probable_bots": 0,
        "processed": 0
    }

    for p in posts:
        try:
            # Normalize text
            p.text = normalize_post(p.text)

            # Extract symbols
            p.symbols = list(set(extract_symbols(p.text, inst_dict)))

            # Filter out posts with no symbols or probable bots
            if not p.symbols:
                filter_stats["no_symbols"] += 1
                continue

            if is_probable_bot(p):
                filter_stats["probable_bots"] += 1
                continue

            clean_posts.append(p)
            filter_stats["processed"] += 1

        except Exception as e:
            logger.warning(f"Failed to clean post from {p.source}: {e}")
            continue

    logger.info(f"Cleaned posts: {filter_stats['processed']}/{filter_stats['total_input']} "
                f"(filtered: {filter_stats['no_symbols']} no symbols, {filter_stats['probable_bots']} bots)")

    if not clean_posts:
        logger.warning(f"No posts passed filtering for {symbol}")
        return {
            "symbol": symbol,
            "posts_found": len(posts),
            "posts_processed": 0,
            "sources": sources_status,
            "resolved_instrument": inst_dict,
            "error": "No valid posts after filtering"
        }

    # Persist, score, and embed
    db = DB()
    processed_count = 0

    for p in clean_posts:
        try:
            # Upsert post
            pk = db.upsert_post(p)

            # Score sentiment
            sentiment = score_text(p.text)
            db.upsert_sentiment(pk, sentiment)

            # Compute and store embedding
            emb = compute_embedding(p.text)
            db.upsert_embedding(pk, emb)

            processed_count += 1
        except Exception as e:
            logger.warning(f"Failed to process post {p.platform_id} from {p.source}: {e}")
            continue

    logger.info(f"Successfully processed {processed_count} posts for {symbol}")

    # Aggregate results
    try:
        result = db.aggregate(inst.symbol, since)
        result["resolved_instrument"] = inst_dict
        result["posts_found"] = len(posts)
        result["posts_processed"] = processed_count
        result["sources"] = sources_status
        logger.info(f"Aggregation complete for {symbol}: {processed_count} posts")
        return result
    except Exception as e:
        logger.error(f"Aggregation failed for {symbol}: {e}")
        raise

def _parse_window(window: str) -> dt.timedelta:
    """
    Parse time window string to timedelta.

    Args:
        window: String like "24h" or "7d"

    Returns:
        timedelta object

    Raises:
        ValueError: If window format is invalid
    """
    try:
        n = int(window[:-1])
        unit = window[-1].lower()

        if unit == 'h':
            return dt.timedelta(hours=n)
        elif unit == 'd':
            return dt.timedelta(days=n)
        else:
            logger.warning(f"Unknown time unit {unit}, defaulting to 24h")
            return dt.timedelta(hours=24)
    except (ValueError, IndexError) as e:
        logger.error(f"Failed to parse window {window}: {e}")
        raise ValueError(f"Invalid window format: {window}. Use format like '24h' or '7d'.")
