# Sentiment Bot - Fintech Sentiment Analysis API

Aggregates and analyzes social media sentiment about financial instruments across multiple platforms: X (Twitter), Reddit, StockTwits, and Discord.

**Features:**
- Real-time sentiment analysis using FinBERT (trained on financial text)
- Multi-source data aggregation (X, Reddit, StockTwits, Discord)
- Semantic embeddings with sentence-transformers for similarity search
- Comprehensive error handling with graceful degradation
- PostgreSQL with pgvector for vector search
- Redis caching for symbol resolution

---

## Quick Start

### 1. Prerequisites

- Python 3.8+
- Docker & Docker Compose
- API Keys for (optional but recommended):
  - **X/Twitter**: OAuth2 Bearer token from [Twitter Developer Portal](https://developer.twitter.com)
  - **Reddit**: OAuth2 credentials from [Reddit Apps](https://www.reddit.com/prefs/apps)
  - **Discord**: Bot token from [Discord Developer Portal](https://discord.com/developers/applications)

### 2. Setup

**Start databases:**
```bash
cd infra
docker-compose up -d  # PostgreSQL + pgvector + Redis
```

**Install dependencies:**
```bash
pip install -r requirements.txt
```

**Configure environment:**
```bash
cp .env.example .env
# Edit .env with your API keys
```

**Example .env:**
```env
# X/Twitter API v2
X_BEARER_TOKEN=YOUR_BEARER_TOKEN

# Reddit OAuth
REDDIT_CLIENT_ID=YOUR_CLIENT_ID
REDDIT_CLIENT_SECRET=YOUR_CLIENT_SECRET
REDDIT_USER_AGENT=sentiment-bot/1.0

# Discord Bot
DISCORD_BOT_TOKEN=YOUR_BOT_TOKEN
DISCORD_GUILD_IDS=123456789,987654321
DISCORD_CHANNEL_ALLOWLIST=channel_id_1,channel_id_2

# Database
DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/sentiment
REDIS_URL=redis://localhost:6379/0

# Features
ALLOW_UNOFFICIAL=false
DRY_RUN=false
```

**Run the API:**
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Access the API:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

---

## API Endpoints

### Health Check
```bash
curl http://localhost:8000/healthz
```

**Response:**
```json
{
  "status": "ok",
  "timestamp": "2025-01-15T10:30:00.123456",
  "version": "1.0.0"
}
```

### Query Sentiment
```bash
curl "http://localhost:8000/query?symbol=AAPL&window=24h"
```

**Parameters:**
- `symbol` (required): Stock symbol or company name (e.g., `AAPL`, `TSLA`, `Apple`)
- `window` (optional, default: `24h`): Time window (`24h`, `7d`, `30d`, etc.)

**Response:**
```json
{
  "symbol": "AAPL",
  "posts_found": 42,
  "posts_processed": 38,
  "sources": {
    "x": 15,
    "reddit": 12,
    "stocktwits": 8,
    "discord": 5
  },
  "sentiment": {
    "avg_polarity": 0.65,
    "avg_subjectivity": 0.52,
    "confidence": 0.78
  },
  "resolved_instrument": {
    "symbol": "AAPL",
    "company_name": "Apple Inc.",
    "cik": "0000320193"
  }
}
```

### Root Endpoint
```bash
curl http://localhost:8000/
```

**Response:**
```json
{
  "service": "Sentiment Bot API",
  "version": "1.0.0",
  "description": "Social media sentiment analysis for financial instruments",
  "endpoints": {
    "health": "/healthz",
    "query": "/query?symbol=AAPL&window=24h",
    "docs": "/docs",
    "redoc": "/redoc"
  }
}
```

---

## Usage Examples

### Example 1: Query with default window
```bash
curl "http://localhost:8000/query?symbol=TSLA"
```

### Example 2: Query with 7-day window
```bash
curl "http://localhost:8000/query?symbol=TSLA&window=7d"
```

### Example 3: Query by company name
```bash
curl "http://localhost:8000/query?symbol=Apple&window=24h"
```

### Example 4: Python client
```python
import requests

response = requests.get(
    "http://localhost:8000/query",
    params={"symbol": "AAPL", "window": "24h"}
)
result = response.json()
print(f"Sentiment for {result['symbol']}: {result['sentiment']['avg_polarity']}")
```

---

## Architecture

```
sentiment-bot/
├── app/
│   ├── main.py                    # FastAPI application
│   ├── config.py                  # Settings management
│   ├── services/
│   │   ├── types.py               # Data models
│   │   ├── resolver.py            # Symbol resolution
│   │   ├── x_client.py            # X/Twitter API v2
│   │   ├── reddit_client.py       # Reddit (PRAW)
│   │   ├── stocktwits_client.py   # StockTwits REST API
│   │   └── discord_client.py      # Discord REST API
│   ├── nlp/
│   │   ├── sentiment.py           # FinBERT sentiment scoring
│   │   ├── embeddings.py          # Sentence-transformers
│   │   ├── clean.py               # Text normalization
│   │   └── bot_filter.py          # Bot detection
│   ├── orchestration/
│   │   └── tasks.py               # Main pipeline
│   └── storage/
│       ├── db.py                  # PostgreSQL operations
│       └── schemas.sql            # DB schema
├── tests/                         # Integration tests
├── infra/
│   └── docker-compose.yaml        # PostgreSQL + Redis
└── requirements.txt
```

## Data Flow

```
Query (symbol, window)
  ↓
Resolve Symbol (cache: Redis)
  ↓
Collect Posts (parallel):
  ├→ X/Twitter API v2
  ├→ Reddit (PRAW)
  ├→ StockTwits REST API
  └→ Discord REST API
  ↓
Clean & Filter:
  ├→ Normalize text (remove URLs, whitespace)
  ├→ Extract symbols (cashtags, company names)
  ├→ Filter bots (heuristics)
  └→ Skip posts without symbols
  ↓
Process & Persist:
  ├→ Score sentiment (FinBERT)
  ├→ Generate embeddings (sentence-transformers)
  └→ Store in PostgreSQL + pgvector
  ↓
Aggregate Results:
  ├→ Average polarity per source
  ├→ Confidence scores
  └→ Count metrics
  ↓
Return JSON Response
```

## Technologies

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Web Framework** | FastAPI 0.109.0 | REST API, auto-docs |
| **Sentiment** | FinBERT (transformers) | Financial sentiment scoring |
| **Embeddings** | sentence-transformers | Semantic similarity |
| **Database** | PostgreSQL + pgvector | Post storage + vector search |
| **Cache** | Redis | Symbol resolution caching |
| **Clients** | httpx | Async HTTP for APIs |
| **Reddit** | PRAW 7.7.1 | Official Reddit API wrapper |
| **Discord** | discord.py 2.3.2 | Discord bot framework |
| **Testing** | pytest 7.4.3 | Integration & unit tests |

## ML Models

- **FinBERT** (ProsusAI/finbert): Pre-trained on financial text corpus
  - Classes: negative, neutral, positive
  - Output: Polarity (-1 to +1), Confidence

- **Sentence-Transformers** (all-MiniLM-L6-v2): Fast semantic embeddings
  - Dimensionality: 384
  - Use case: Vector similarity search in pgvector

## Configuration

All settings via environment variables (`.env`):

**API Keys (Optional):**
- `X_BEARER_TOKEN` - X/Twitter API v2 bearer token
- `REDDIT_CLIENT_ID` & `REDDIT_CLIENT_SECRET` - Reddit OAuth
- `DISCORD_BOT_TOKEN` - Discord bot token
- `ST_FIRESTREAM_URL` & `ST_TOKEN` - StockTwits premium (unused in MVP)

**Database:**
- `DATABASE_URL` - PostgreSQL connection string (default: localhost:5432)
- `REDIS_URL` - Redis connection string (default: localhost:6379)

**Feature Flags:**
- `ALLOW_UNOFFICIAL` - Allow unofficial/third-party APIs (default: false)
- `DRY_RUN` - Test mode without actual API calls (default: false)

## Testing

Run all tests:
```bash
pytest tests/
```

Run specific test file:
```bash
pytest tests/test_api_endpoints.py -v
```

Run with coverage:
```bash
pytest tests/ --cov=app
```

## Running Tests

The test suite includes:
- **API endpoint tests** - Validate request/response handling
- **NLP tests** - Sentiment, embeddings, text cleaning
- **API client tests** - Mocked external API responses
- **Pipeline tests** - End-to-end orchestration

## Error Handling

The API gracefully handles failures:

- **Single source fails**: Other sources continue, partial results returned
- **Model loading fails**: Falls back to heuristic sentiment scoring
- **Rate limit**: Stops collection for that source, continues others
- **Invalid symbol**: Returns 400 with clear error message
- **Network error**: Logs warning, empty response from that source

## Compliance

- **Official APIs only** - Uses official endpoints (X v2, Reddit official, StockTwits public, Discord)
- **Rate limiting** - Respects API rate limits, backs off on 429
- **No credential storage** - All credentials from environment variables
- **Discord security** - Only accesses configured guilds/channels
- **Data privacy** - Posts not stored beyond analysis window

## Troubleshooting

**"No posts found" error:**
- Verify API credentials are correct
- Check time window (try `7d` instead of `24h`)
- Ensure symbol is valid (try full company name)

**"Failed to load FinBERT" warning:**
- Model will fall back to heuristics, results still valid
- Requires ~500MB disk space for model download on first run

**Database connection error:**
- Verify Docker containers are running: `docker-compose ps`
- Check connection string in `.env`

**Rate limiting:**
- X/Twitter: 450 requests/15 min
- Reddit: 60 requests/min
- API will retry automatically with backoff

## Future Enhancements

Phase 2+ improvements:
- Sarcasm detection with specialized models
- Entity extraction (companies, individuals)
- Temporal analysis (sentiment trends)
- Sentiment-weighted price correlation
- Custom alert thresholds
- Batch processing for historical data
- WebSocket streaming updates
