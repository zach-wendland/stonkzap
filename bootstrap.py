import os, textwrap, pathlib

base = pathlib.Path("sentiment-bot")
dirs = [
    "infra/k8s", "app/routers", "app/services", "app/nlp",
    "app/storage", "app/orchestration", "tests", "docs"
]
for d in dirs:
    (base/d).mkdir(parents=True, exist_ok=True)
    (base/d/"__init__.py").touch()

# Root __init__
(base/"app"/"__init__.py").touch()

# Environment template
(base/".env.example").write_text(textwrap.dedent("""\
# Required API Keys
X_BEARER_TOKEN=your_twitter_bearer_token
REDDIT_CLIENT_ID=your_reddit_client_id
REDDIT_CLIENT_SECRET=your_reddit_secret
REDDIT_USER_AGENT=sentiment-bot/1.0 by yourname

# Optional Partners
ST_FIRESTREAM_URL=
ST_TOKEN=

# Discord (only for servers you control, with Message Content intent)
DISCORD_BOT_TOKEN=
DISCORD_GUILD_IDS=
DISCORD_CHANNEL_ALLOWLIST=

# Feature Flags
ALLOW_UNOFFICIAL=false
DRY_RUN=false

# Database
DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/sentiment
REDIS_URL=redis://localhost:6379/0
"""))

# Docker Compose
(base/"infra"/"docker-compose.yaml").write_text(textwrap.dedent("""\
version: "3.9"
services:
  db:
    image: pgvector/pgvector:0.7.4-pg16
    environment:
      POSTGRES_USER: user
      POSTGRES_PASSWORD: pass
      POSTGRES_DB: sentiment
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data

volumes:
  postgres_data:
  redis_data:
"""))

# Database Schema
(base/"app"/"storage"/"schemas.sql").write_text(textwrap.dedent("""\
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS source_accounts (
    source TEXT NOT NULL,
    author_id TEXT NOT NULL,
    handle TEXT,
    follower_count INT,
    last_seen TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (source, author_id)
);

CREATE TABLE IF NOT EXISTS social_posts (
    id BIGSERIAL PRIMARY KEY,
    source TEXT NOT NULL,
    platform_id TEXT NOT NULL,
    author_id TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    ingested_at TIMESTAMPTZ DEFAULT NOW(),
    text TEXT NOT NULL,
    symbols TEXT[] NOT NULL DEFAULT '{}',
    urls TEXT[] DEFAULT '{}',
    lang TEXT,
    reply_to_id TEXT,
    repost_of_id TEXT,
    like_count INT,
    reply_count INT,
    repost_count INT,
    follower_count INT,
    permalink TEXT,
    UNIQUE (source, platform_id)
);

CREATE TABLE IF NOT EXISTS post_embeddings (
    post_pk BIGINT PRIMARY KEY REFERENCES social_posts(id) ON DELETE CASCADE,
    emb VECTOR(768)
);

CREATE TABLE IF NOT EXISTS sentiment (
    post_pk BIGINT PRIMARY KEY REFERENCES social_posts(id) ON DELETE CASCADE,
    polarity REAL,
    subjectivity REAL,
    sarcasm_prob REAL,
    confidence REAL,
    model TEXT
);

CREATE TABLE IF NOT EXISTS resolver_cache (
    query TEXT PRIMARY KEY,
    symbol TEXT,
    cik TEXT,
    isin TEXT,
    figi TEXT,
    company_name TEXT,
    cached_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_social_posts_symbols ON social_posts USING GIN (symbols);
CREATE INDEX IF NOT EXISTS idx_social_posts_created ON social_posts (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_social_posts_source_created ON social_posts (source, created_at DESC);
"""))

# Requirements
(base/"requirements.txt").write_text(textwrap.dedent("""\
fastapi==0.109.0
uvicorn[standard]==0.27.0
pydantic==2.5.3
pydantic-settings==2.1.0
psycopg[binary]==3.1.18
redis==5.0.1
httpx==0.26.0
numpy==1.26.3
python-dotenv==1.0.0
"""))

# Config
(base/"app"/"config.py").write_text(textwrap.dedent("""\
from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    # API Keys
    x_bearer_token: str = ""
    reddit_client_id: str = ""
    reddit_client_secret: str = ""
    reddit_user_agent: str = "sentiment-bot/1.0"

    # Partners
    st_firestream_url: str = ""
    st_token: str = ""

    # Discord
    discord_bot_token: str = ""
    discord_guild_ids: str = ""
    discord_channel_allowlist: str = ""

    # Flags
    allow_unofficial: bool = False
    dry_run: bool = False

    # Database
    database_url: str = "postgresql+psycopg://user:pass@localhost:5432/sentiment"
    redis_url: str = "redis://localhost:6379/0"

    class Config:
        env_file = ".env"
        case_sensitive = False

@lru_cache()
def get_settings():
    return Settings()
"""))

# Types
(base/"app"/"services"/"types.py").write_text(textwrap.dedent("""\
from pydantic import BaseModel
from typing import Literal, Optional, List
from datetime import datetime

class SocialPost(BaseModel):
    source: Literal["reddit", "x", "stocktwits", "yahoo_forum", "discord"]
    platform_id: str
    author_id: str
    author_handle: Optional[str] = None
    created_at: datetime
    text: str
    symbols: List[str] = []
    urls: List[str] = []
    lang: Optional[str] = None
    reply_to_id: Optional[str] = None
    repost_of_id: Optional[str] = None
    like_count: Optional[int] = None
    reply_count: Optional[int] = None
    repost_count: Optional[int] = None
    follower_count: Optional[int] = None
    permalink: Optional[str] = None

class SentimentScore(BaseModel):
    polarity: float
    subjectivity: float
    sarcasm_prob: float
    confidence: float
    model: str = "textblob"

class ResolvedInstrument(BaseModel):
    symbol: str
    cik: Optional[str] = None
    isin: Optional[str] = None
    figi: Optional[str] = None
    company_name: str
"""))

# Database Layer
db_content = '''import os
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
'''
(base/"app"/"storage"/"db.py").write_text(db_content)

# NLP - Clean
(base/"app"/"nlp"/"clean.py").write_text(textwrap.dedent("""\
import re
from typing import List

def normalize_post(t: str) -> str:
    # Remove URLs
    t = re.sub(r'https?://\S+', '', t)
    # Remove excessive whitespace
    t = re.sub(r'\s+', ' ', t)
    t = t.strip()
    return t

def extract_symbols(t: str, inst: dict) -> List[str]:
    # Extract cashtags
    tickers = set(re.findall(r'\$([A-Z]{1,5})(?![A-Z])', t))

    # Add instrument symbol if mentioned
    if inst["symbol"] in t.upper() or inst["symbol"] in tickers:
        tickers.add(inst["symbol"])

    # Add if company name mentioned
    if inst["company_name"] and inst["company_name"].upper() in t.upper():
        tickers.add(inst["symbol"])

    return list(tickers)
"""))

# NLP - Sentiment (TextBlob stub)
(base/"app"/"nlp"/"sentiment.py").write_text(textwrap.dedent("""\
from app.services.types import SentimentScore

def score_text(text: str) -> SentimentScore:
    # Placeholder using simple heuristics
    # TODO: Replace with FinBERT or financial RoBERTa

    positive_words = ['bullish', 'moon', 'buy', 'long', 'growth', 'profit', 'gain', 'up']
    negative_words = ['bearish', 'crash', 'sell', 'short', 'loss', 'down', 'dump']

    text_lower = text.lower()
    pos_count = sum(1 for word in positive_words if word in text_lower)
    neg_count = sum(1 for word in negative_words if word in text_lower)

    total = pos_count + neg_count
    if total == 0:
        polarity = 0.0
    else:
        polarity = (pos_count - neg_count) / total

    # Simple subjectivity based on length and punctuation
    subjectivity = min(1.0, (len(text) / 280) * 0.7)

    # Sarcasm detection placeholder
    sarcasm_indicators = ['yeah right', 'sure', '🙄']
    sarcasm_prob = 0.8 if any(ind in text_lower for ind in sarcasm_indicators) else 0.1

    confidence = 0.6 if total > 0 else 0.3

    return SentimentScore(
        polarity=max(-1.0, min(1.0, polarity)),
        subjectivity=subjectivity,
        sarcasm_prob=sarcasm_prob,
        confidence=confidence,
        model="simple_heuristic"
    )
"""))

# NLP - Embeddings
(base/"app"/"nlp"/"embeddings.py").write_text(textwrap.dedent("""\
import numpy as np

def compute_embedding(text: str) -> np.ndarray:
    # Placeholder: simple hash-based embedding
    # TODO: Replace with sentence-transformers or similar
    np.random.seed(hash(text) % (2**32))
    emb = np.random.randn(768).astype(np.float32)
    # Normalize
    emb = emb / np.linalg.norm(emb)
    return emb
"""))

# NLP - Bot Filter
(base/"app"/"nlp"/"bot_filter.py").write_text(textwrap.dedent("""\
from app.services.types import SocialPost

def is_probable_bot(post: SocialPost) -> bool:
    # Simple heuristics - expand as needed

    # Check for very short posts with just tickers
    if len(post.text) < 20 and len(post.symbols) > 0:
        return True

    # Check for repetitive patterns
    if post.text.count('$') > 5:
        return True

    # Very high post frequency accounts (would need historical data)
    # For now, just basic checks

    return False
"""))

# Services - Resolver
(base/"app"/"services"/"resolver.py").write_text(textwrap.dedent("""\
import httpx
from typing import Optional
from app.services.types import ResolvedInstrument
from app.storage.db import DB

# Simple symbol map for common tickers
SYMBOL_MAP = {
    "APPLE": "AAPL",
    "TESLA": "TSLA",
    "MICROSOFT": "MSFT",
    "AMAZON": "AMZN",
    "GOOGLE": "GOOGL",
    "META": "META",
    "NVIDIA": "NVDA",
}

def resolve(query: str) -> ResolvedInstrument:
    # Check cache first
    db = DB()
    cached = db.get_cached_resolution(query.upper())
    if cached:
        return ResolvedInstrument(**cached)

    # Normalize query
    query_upper = query.upper().strip('$')

    # Check if it's already a ticker
    if len(query_upper) <= 5 and query_upper.isalpha():
        result = ResolvedInstrument(
            symbol=query_upper,
            company_name=query_upper
        )
    # Check if it's a company name
    elif query_upper in SYMBOL_MAP:
        symbol = SYMBOL_MAP[query_upper]
        result = ResolvedInstrument(
            symbol=symbol,
            company_name=query
        )
    else:
        # Default fallback
        result = ResolvedInstrument(
            symbol=query_upper,
            company_name=query
        )

    # Cache the result
    db.cache_resolution(
        query=query.upper(),
        symbol=result.symbol,
        cik=result.cik,
        isin=result.isin,
        figi=result.figi,
        company_name=result.company_name
    )

    return result
"""))

# Services - Reddit Client
(base/"app"/"services"/"reddit_client.py").write_text(textwrap.dedent("""\
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
"""))

# Services - X Client
(base/"app"/"services"/"x_client.py").write_text(textwrap.dedent("""\
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
"""))

# Services - StockTwits Client
(base/"app"/"services"/"stocktwits_client.py").write_text(textwrap.dedent("""\
from typing import List
from datetime import datetime
from app.services.types import SocialPost
from app.config import get_settings

def collect_stocktwits(inst: dict, since: datetime) -> List[SocialPost]:
    settings = get_settings()

    if settings.st_firestream_url and settings.st_token:
        # TODO: Implement Firestream SSE connection
        pass

    # TODO: Fallback to allowed REST endpoints if available
    # Note: StockTwits has rate limits on public API

    return []
"""))

# Services - Discord Client
(base/"app"/"services"/"discord_client.py").write_text(textwrap.dedent("""\
from typing import List
from datetime import datetime
from app.services.types import SocialPost
from app.config import get_settings

def collect_discord(inst: dict, since: datetime) -> List[SocialPost]:
    settings = get_settings()

    if not settings.discord_bot_token:
        return []

    # TODO: Implement Discord Gateway client
    # - Only connect to guilds in DISCORD_GUILD_IDS
    # - Only read from channels in DISCORD_CHANNEL_ALLOWLIST
    # - Message Content intent must be enabled
    # - Extract cashtags from messages
    # - Never read DMs or non-allowlisted channels

    return []
"""))

# Orchestration
(base/"app"/"orchestration"/"tasks.py").write_text(textwrap.dedent("""\
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
"""))

# Main FastAPI App
(base/"app"/"main.py").write_text(textwrap.dedent("""\
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from app.orchestration.tasks import aggregate_social, healthcheck
from app.config import get_settings

app = FastAPI(
    title="Sentiment Bot API",
    description="Social media sentiment analysis for financial instruments",
    version="1.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/healthz")
def health_check():
    return healthcheck()

@app.get("/query")
def query_sentiment(
    symbol: str = Query(..., min_length=1, description="Stock symbol or company name"),
    window: str = Query("24h", regex="^[0-9]+[hd]$", description="Time window (e.g., 24h, 7d)")
):
    try:
        result = aggregate_social(symbol.upper(), window)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
def root():
    return {
        "service": "Sentiment Bot API",
        "endpoints": {
            "health": "/healthz",
            "query": "/query?symbol=AAPL&window=24h"
        }
    }
"""))

# Tests
(base/"tests"/"test_health.py").write_text(textwrap.dedent("""\
from app.orchestration.tasks import healthcheck

def test_healthcheck():
    result = healthcheck()
    assert "status" in result
    assert result["status"] == "ok"
"""))

(base/"tests"/"test_resolver.py").write_text(textwrap.dedent("""\
from app.services.resolver import resolve

def test_resolve_symbol():
    result = resolve("AAPL")
    assert result.symbol == "AAPL"
    assert result.company_name is not None

def test_resolve_company_name():
    result = resolve("Apple")
    assert result.symbol == "AAPL"
"""))

# .env file
(base/".env").write_text(textwrap.dedent("""\
# Copy from .env.example and fill in your credentials
DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/sentiment
REDIS_URL=redis://localhost:6379/0
DRY_RUN=false
ALLOW_UNOFFICIAL=false
"""))

# .gitignore
(base/".gitignore").write_text(textwrap.dedent("""\
__pycache__/
*.py[cod]
*$py.class
.env
.venv/
venv/
*.log
.DS_Store
"""))

# README
(base/"README.md").write_text(textwrap.dedent("""\
# Sentiment Bot

Social media sentiment analysis for financial instruments.

## Setup

1. Start databases:
```bash
   cd infra
   docker-compose up -d
```

2. Install dependencies:
```bash
   pip install -r requirements.txt
```

3. Configure environment:
```bash
   cp .env.example .env
   # Edit .env with your API keys
```

4. Run the API:
```bash
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

5. Test:
```bash
   curl http://localhost:8000/healthz
   curl "http://localhost:8000/query?symbol=AAPL&window=24h"
```

## Architecture

- `app/main.py` - FastAPI application
- `app/orchestration/` - Task coordination
- `app/services/` - External API clients
- `app/nlp/` - Text processing and ML
- `app/storage/` - Database layer
- `infra/` - Docker and Kubernetes configs

## Data Flow

1. Query comes in for a symbol
2. Resolve symbol to standard identifiers
3. Fetch posts from Reddit, X, StockTwits, Discord
4. Clean text and extract symbols
5. Score sentiment and compute embeddings
6. Aggregate and return results

## Compliance

- Only use official APIs where available
- Discord: Only servers you own, Message Content intent enabled
- Rate limiting and backoff on all external calls
- Set ALLOW_UNOFFICIAL=false in production
- Enable DRY_RUN=true for testing without actual API calls
"""))

print("✓ Sentiment bot scaffold created at ./sentiment-bot")
print("\nNext steps:")
print("1. cd sentiment-bot")
print("2. python3 -m pip install -r requirements.txt")
print("3. cd infra && docker-compose up -d")
print("4. cd .. && uvicorn app.main:app --reload")
