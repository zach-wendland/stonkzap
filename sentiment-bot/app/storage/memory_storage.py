"""
In-memory storage backend as an alternative to PostgreSQL.

This allows the application to run without Docker or external databases.
"""

from typing import Dict, List, Optional
from datetime import datetime, timedelta
from collections import defaultdict
import threading
from app.services.types import SocialPost, SentimentScore
from app.logging_config import get_logger

logger = get_logger(__name__)


class InMemoryStorage:
    """In-memory storage backend using Python data structures."""

    def __init__(self):
        self._lock = threading.Lock()
        self._posts: Dict[int, Dict] = {}
        self._post_counter = 1
        self._embeddings: Dict[int, bytes] = {}
        self._sentiment: Dict[int, Dict] = {}
        self._resolver_cache: Dict[str, Dict] = {}
        self._post_index: Dict[tuple, int] = {}  # (source, platform_id) -> post_pk
        logger.info("Initialized in-memory storage backend")

    def upsert_post(self, p: SocialPost) -> int:
        """Insert or update a post."""
        with self._lock:
            # Check if post exists
            key = (p.source, p.platform_id)
            if key in self._post_index:
                pk = self._post_index[key]
                # Update ingested_at
                self._posts[pk]['ingested_at'] = datetime.now()
                logger.debug(f"Updated existing post {pk}")
                return pk

            # Create new post
            pk = self._post_counter
            self._post_counter += 1

            self._posts[pk] = {
                'id': pk,
                'source': p.source,
                'platform_id': p.platform_id,
                'author_id': p.author_id,
                'created_at': p.created_at,
                'ingested_at': datetime.now(),
                'text': p.text,
                'symbols': p.symbols,
                'urls': p.urls or [],
                'lang': p.lang,
                'reply_to_id': p.reply_to_id,
                'repost_of_id': p.repost_of_id,
                'like_count': p.like_count,
                'reply_count': p.reply_count,
                'repost_count': p.repost_count,
                'follower_count': p.follower_count,
                'permalink': p.permalink
            }

            self._post_index[key] = pk
            logger.debug(f"Created new post {pk} from {p.source}")
            return pk

    def upsert_sentiment(self, pk: int, s: SentimentScore) -> None:
        """Insert or update sentiment score for a post."""
        with self._lock:
            if pk not in self._posts:
                logger.warning(f"Post {pk} not found for sentiment update")
                return

            self._sentiment[pk] = {
                'post_pk': pk,
                'polarity': s.polarity,
                'subjectivity': s.subjectivity,
                'sarcasm_prob': s.sarcasm_prob,
                'confidence': s.confidence,
                'model': s.model
            }
            logger.debug(f"Updated sentiment for post {pk}")

    def upsert_embedding(self, pk: int, emb: bytes) -> None:
        """Insert or update embedding for a post."""
        with self._lock:
            if pk not in self._posts:
                logger.warning(f"Post {pk} not found for embedding update")
                return

            self._embeddings[pk] = emb
            logger.debug(f"Updated embedding for post {pk}")

    def aggregate(self, symbol: str, since: datetime) -> Dict:
        """Aggregate sentiment data for a symbol since a given time."""
        with self._lock:
            # Find all posts with the symbol
            matching_posts = []
            for pk, post in self._posts.items():
                if symbol in post['symbols'] and post['created_at'] >= since:
                    if pk in self._sentiment:
                        matching_posts.append({
                            'pk': pk,
                            'source': post['source'],
                            'sentiment': self._sentiment[pk]
                        })

            if not matching_posts:
                return {
                    "symbol": symbol,
                    "window_since": since.isoformat(),
                    "count": 0,
                    "weighted_sentiment": 0.0,
                    "sources": {}
                }

            # Aggregate by source
            source_counts = defaultdict(int)
            source_polarities = defaultdict(list)

            for post in matching_posts:
                source = post['source']
                polarity = post['sentiment']['polarity']
                source_counts[source] += 1
                source_polarities[source].append(polarity)

            # Calculate weighted sentiment
            total_count = sum(source_counts.values())
            total_polarity = sum(
                sum(source_polarities[source])
                for source in source_counts
            )

            return {
                "symbol": symbol,
                "window_since": since.isoformat(),
                "count": total_count,
                "weighted_sentiment": total_polarity / total_count if total_count > 0 else 0.0,
                "sources": dict(source_counts)
            }

    def cache_resolution(self, query: str, symbol: str, cik: Optional[str],
                         isin: Optional[str], figi: Optional[str], company_name: str):
        """Cache a symbol resolution."""
        with self._lock:
            self._resolver_cache[query] = {
                'symbol': symbol,
                'cik': cik,
                'isin': isin,
                'figi': figi,
                'company_name': company_name,
                'cached_at': datetime.now()
            }
            logger.debug(f"Cached resolution for {query} -> {symbol}")

    def get_cached_resolution(self, query: str) -> Optional[Dict]:
        """Get a cached symbol resolution."""
        with self._lock:
            if query not in self._resolver_cache:
                return None

            cached = self._resolver_cache[query]
            # Check if cache is still valid (7 days)
            if datetime.now() - cached['cached_at'] > timedelta(days=7):
                del self._resolver_cache[query]
                return None

            return {
                'symbol': cached['symbol'],
                'cik': cached['cik'],
                'isin': cached['isin'],
                'figi': cached['figi'],
                'company_name': cached['company_name']
            }

    def get_stats(self) -> Dict:
        """Get storage statistics."""
        with self._lock:
            return {
                'total_posts': len(self._posts),
                'posts_with_sentiment': len(self._sentiment),
                'posts_with_embeddings': len(self._embeddings),
                'cached_resolutions': len(self._resolver_cache)
            }

    def clear(self):
        """Clear all data (useful for testing)."""
        with self._lock:
            self._posts.clear()
            self._embeddings.clear()
            self._sentiment.clear()
            self._resolver_cache.clear()
            self._post_index.clear()
            self._post_counter = 1
            logger.info("Cleared all in-memory storage")
