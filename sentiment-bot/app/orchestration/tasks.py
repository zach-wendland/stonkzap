import datetime as dt
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

def healthcheck() -> Dict:
    return {"status": "ok", "timestamp": dt.datetime.utcnow().isoformat()}

def aggregate_social(symbol: str, window: str = "24h") -> Dict:
    # Resolve symbol
    inst = resolve(symbol)
    inst_dict = inst.model_dump()

    # Parse time window
    since = dt.datetime.utcnow() - _parse_window(window)

    # Collect from all sources
    posts: List[SocialPost] = []
    posts.extend(search_reddit_bundle(inst_dict, since))
    posts.extend(search_x_bundle(inst_dict, since))
    posts.extend(collect_stocktwits(inst_dict, since))
    posts.extend(collect_discord(inst_dict, since))

    # Clean and filter
    clean_posts = []
    for p in posts:
        # Normalize text
        p.text = normalize_post(p.text)

        # Extract symbols
        p.symbols = list(set(extract_symbols(p.text, inst_dict)))

        # Filter out posts with no symbols or probable bots
        if not p.symbols or is_probable_bot(p):
            continue

        clean_posts.append(p)

    # Persist, score, and embed
    db = DB()
    for p in clean_posts:
        # Upsert post
        pk = db.upsert_post(p)

        # Score sentiment
        sentiment = score_text(p.text)
        db.upsert_sentiment(pk, sentiment)

        # Compute and store embedding
        emb = compute_embedding(p.text)
        db.upsert_embedding(pk, emb)

    # Aggregate results
    result = db.aggregate(inst.symbol, since)
    result["resolved_instrument"] = inst_dict
    result["posts_processed"] = len(clean_posts)

    return result

def _parse_window(window: str) -> dt.timedelta:
    try:
        n = int(window[:-1])
        unit = window[-1].lower()

        if unit == 'h':
            return dt.timedelta(hours=n)
        elif unit == 'd':
            return dt.timedelta(days=n)
        else:
            return dt.timedelta(hours=24)
    except (ValueError, IndexError):
        return dt.timedelta(hours=24)
