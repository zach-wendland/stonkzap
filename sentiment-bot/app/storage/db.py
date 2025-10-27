import os
import psycopg
import numpy as np
from datetime import datetime, timedelta
from typing import Optional, List, Dict
from app.services.types import SocialPost, SentimentScore
from app.config import get_settings

class DB:
    def __init__(self):
        settings = get_settings()
        self.conn = psycopg.connect(settings.database_url, autocommit=True)
        self._init_schema()

    def _init_schema(self):
        schema_path = os.path.join(os.path.dirname(__file__), "schemas.sql")
        with open(schema_path) as f:
            with self.conn.cursor() as c:
                c.execute(f.read())

    def upsert_post(self, p: SocialPost) -> int:
        with self.conn.cursor() as c:
            c.execute("""
                INSERT INTO social_posts
                (source, platform_id, author_id, created_at, text, symbols, urls, lang,
                 reply_to_id, repost_of_id, like_count, reply_count, repost_count,
                 follower_count, permalink)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (source, platform_id) DO UPDATE SET ingested_at = NOW()
                RETURNING id
            """, (
                p.source, p.platform_id, p.author_id, p.created_at, p.text,
                p.symbols, p.urls, p.lang, p.reply_to_id, p.repost_of_id,
                p.like_count, p.reply_count, p.repost_count, p.follower_count, p.permalink
            ))
            return c.fetchone()[0]

    def upsert_sentiment(self, pk: int, s: SentimentScore) -> None:
        with self.conn.cursor() as c:
            c.execute("""
                INSERT INTO sentiment (post_pk, polarity, subjectivity, sarcasm_prob, confidence, model)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (post_pk) DO UPDATE SET
                    polarity = EXCLUDED.polarity,
                    subjectivity = EXCLUDED.subjectivity,
                    sarcasm_prob = EXCLUDED.sarcasm_prob,
                    confidence = EXCLUDED.confidence,
                    model = EXCLUDED.model
            """, (pk, s.polarity, s.subjectivity, s.sarcasm_prob, s.confidence, s.model))

    def upsert_embedding(self, pk: int, emb: np.ndarray) -> None:
        with self.conn.cursor() as c:
            c.execute("""
                INSERT INTO post_embeddings (post_pk, emb)
                VALUES (%s, %s)
                ON CONFLICT (post_pk) DO UPDATE SET emb = EXCLUDED.emb
            """, (pk, emb.tobytes()))

    def aggregate(self, symbol: str, since: datetime) -> Dict:
        with self.conn.cursor() as c:
            c.execute("""
                SELECT
                    COUNT(*) as count,
                    AVG(s.polarity) as avg_polarity,
                    STDDEV(s.polarity) as stddev_polarity,
                    p.source,
                    COUNT(*) as source_count
                FROM social_posts p
                JOIN sentiment s ON s.post_pk = p.id
                WHERE %s = ANY(p.symbols) AND p.created_at >= %s
                GROUP BY p.source
            """, (symbol, since))

            results = c.fetchall()

            if not results:
                return {
                    "symbol": symbol,
                    "window_since": since.isoformat(),
                    "count": 0,
                    "weighted_sentiment": 0.0,
                    "sources": {}
                }

            total_count = sum(r[4] for r in results)
            total_polarity = sum(r[1] * r[4] if r[1] else 0 for r in results)

            source_breakdown = {r[3]: r[4] for r in results}

            return {
                "symbol": symbol,
                "window_since": since.isoformat(),
                "count": total_count,
                "weighted_sentiment": total_polarity / total_count if total_count > 0 else 0.0,
                "sources": source_breakdown
            }

    def cache_resolution(self, query: str, symbol: str, cik: Optional[str],
                        isin: Optional[str], figi: Optional[str], company_name: str):
        with self.conn.cursor() as c:
            c.execute("""
                INSERT INTO resolver_cache (query, symbol, cik, isin, figi, company_name)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (query) DO UPDATE SET
                    symbol = EXCLUDED.symbol,
                    cik = EXCLUDED.cik,
                    isin = EXCLUDED.isin,
                    figi = EXCLUDED.figi,
                    company_name = EXCLUDED.company_name,
                    cached_at = NOW()
            """, (query, symbol, cik, isin, figi, company_name))

    def get_cached_resolution(self, query: str) -> Optional[Dict]:
        with self.conn.cursor() as c:
            c.execute("""
                SELECT symbol, cik, isin, figi, company_name
                FROM resolver_cache
                WHERE query = %s AND cached_at > NOW() - INTERVAL '7 days'
            """, (query,))
            row = c.fetchone()
            if row:
                return {
                    "symbol": row[0],
                    "cik": row[1],
                    "isin": row[2],
                    "figi": row[3],
                    "company_name": row[4]
                }
            return None
