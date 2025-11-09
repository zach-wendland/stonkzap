# Sentiment Bot

Social media sentiment analysis for financial instruments.

**No Docker required!** Uses in-memory storage by default.

## Quick Start

1. **Install dependencies:**
```bash
pip install -r requirements.txt
```

2. **Run the API:**
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

3. **Test:**
```bash
# Health check
curl http://localhost:8000/healthz

# Query sentiment
curl "http://localhost:8000/query?symbol=AAPL&window=24h"

# View API docs
open http://localhost:8000/docs
```

That's it! No Docker, no databases, no complex setup.

## CLI Tool

Test sentiment analysis without the web server:

```bash
# Run built-in examples
python3 cli.py --test

# Analyze single text
python3 cli.py --text "AAPL to the moon! 🚀" --symbol AAPL

# Batch process a file
python3 cli.py --file posts.txt --symbol TSLA

# Adjust logging
python3 cli.py --test --log-level DEBUG
```

## Testing

Run the comprehensive test suite:

```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_sentiment.py -v

# Run with coverage
pytest tests/ --cov=app --cov-report=html
```

**Test Coverage:** 36 passing tests covering sentiment analysis, text cleaning, and API endpoints.

## Architecture

### Storage Backends

**In-Memory (Default):**
- No external dependencies
- Perfect for development and testing
- Data persists only during runtime
- Thread-safe implementation

**PostgreSQL (Optional):**
- Set `USE_POSTGRES=true` in `.env`
- Use cloud-hosted database (Supabase, Neon, etc.) or local PostgreSQL
- Persistent storage with pgvector support
- See `docs/DATABASE_INTEGRATION_GUIDE.md` for setup options

### Components

- `app/main.py` - FastAPI application with rate limiting and logging
- `app/orchestration/` - Task coordination and aggregation logic
- `app/services/` - External API clients (Reddit, X, StockTwits, Discord)
- `app/nlp/` - Text processing, sentiment analysis, embeddings
- `app/storage/` - Database abstraction layer (memory or PostgreSQL)
- `cli.py` - Command-line testing tool
- `tests/` - Comprehensive test suite

### Data Flow

1. Query comes in for a symbol (e.g., AAPL)
2. Resolve symbol to standard identifiers
3. Fetch posts from social media sources
4. Clean text and extract ticker symbols
5. Score sentiment with enhanced heuristics
6. Compute embeddings for similarity search
7. Aggregate and return results

## Sentiment Analysis

The sentiment engine uses enhanced heuristics with:

- **Financial Lexicon**: Domain-specific positive/negative word lists
- **Intensifiers**: "very good" scores higher than "good"
- **Negations**: "not good" flips to negative
- **Emoji Sentiment**: 🚀📈💎 = positive, 📉💀😭 = negative
- **Sarcasm Detection**: Identifies phrases like "yeah right" and 🙄
- **Confidence Scoring**: Based on text features and sarcasm

**Future:** Replace with FinBERT or financial RoBERTa for production.

## Configuration

Edit `.env` to customize behavior:

```bash
# Logging
LOG_LEVEL=INFO  # DEBUG, INFO, WARNING, ERROR

# Rate Limiting
RATE_LIMIT_ENABLED=true
RATE_LIMIT_REQUESTS=100
RATE_LIMIT_WINDOW=60

# Feature Flags
DRY_RUN=false  # Test mode without external API calls
ALLOW_UNOFFICIAL=false  # Enable unofficial data sources

# Database (optional)
USE_POSTGRES=false  # Set to true to use PostgreSQL
DATABASE_URL=  # Connection string if using PostgreSQL
```

## Advanced Setup (Optional)

### Using PostgreSQL

If you need persistent storage:

1. **Set up PostgreSQL:**

   Choose one of these options:
   - **Cloud-hosted (Recommended):** Supabase, Neon, DigitalOcean, AWS RDS
   - **Local installation:** macOS (Homebrew), Linux (apt), Windows (installer)

   See `docs/DATABASE_INTEGRATION_GUIDE.md` for detailed setup instructions for each option.

2. **Configure environment:**
```bash
# In .env
USE_POSTGRES=true
DATABASE_URL=postgresql+psycopg://user:pass@your-host:5432/sentiment
```

3. **Verify setup:**
```bash
python verify_database.py
```

4. **Start the application:**
```bash
uvicorn app.main:app --reload
```

The schema will be automatically initialized on first run.

### API Keys

To collect real social media data, add API keys to `.env`:

```bash
# Twitter/X
X_BEARER_TOKEN=your_token

# Reddit
REDDIT_CLIENT_ID=your_client_id
REDDIT_CLIENT_SECRET=your_secret
REDDIT_USER_AGENT=sentiment-bot/1.0

# StockTwits (Partner API)
ST_FIRESTREAM_URL=your_url
ST_TOKEN=your_token

# Discord (only for servers you own!)
DISCORD_BOT_TOKEN=your_token
DISCORD_GUILD_IDS=comma,separated,ids
DISCORD_CHANNEL_ALLOWLIST=comma,separated,ids
```

## API Endpoints

### GET /healthz
Health check endpoint.

**Response:**
```json
{
  "status": "ok",
  "timestamp": "2025-10-28T18:00:00"
}
```

### GET /query
Query sentiment for a symbol.

**Parameters:**
- `symbol` (required): Stock symbol or company name
- `window` (optional): Time window, default "24h" (e.g., "7d", "24h")

**Example:**
```bash
curl "http://localhost:8000/query?symbol=AAPL&window=24h"
```

**Response:**
```json
{
  "symbol": "AAPL",
  "window_since": "2025-10-27T18:00:00",
  "count": 0,
  "weighted_sentiment": 0.0,
  "sources": {},
  "resolved_instrument": {
    "symbol": "AAPL",
    "company_name": "Apple",
    "cik": null,
    "isin": null,
    "figi": null
  },
  "posts_processed": 0
}
```

### GET /docs
Interactive API documentation (Swagger UI).

## Compliance

- **Official APIs Only**: Use official APIs where available
- **Discord**: Only connect to servers you own with Message Content intent enabled
- **Rate Limiting**: Built-in rate limiting on all external calls
- **Privacy**: Never read DMs or non-allowlisted channels
- **Production**: Set `ALLOW_UNOFFICIAL=false` in production
- **Testing**: Enable `DRY_RUN=true` to test without external API calls

## Development

### Project Structure

```
sentiment-bot/
├── app/
│   ├── config.py              # Settings and configuration
│   ├── logging_config.py      # Logging setup
│   ├── main.py                # FastAPI application
│   ├── nlp/                   # Text processing and ML
│   │   ├── bot_filter.py      # Bot detection
│   │   ├── clean.py           # Text normalization
│   │   ├── embeddings.py      # Vector embeddings
│   │   └── sentiment.py       # Sentiment scoring
│   ├── orchestration/
│   │   └── tasks.py           # Core business logic
│   ├── services/              # External API clients
│   │   ├── discord_client.py
│   │   ├── reddit_client.py
│   │   ├── resolver.py        # Symbol resolution
│   │   ├── stocktwits_client.py
│   │   ├── types.py           # Pydantic models
│   │   └── x_client.py
│   └── storage/
│       ├── db.py              # Database abstraction
│       ├── memory_storage.py  # In-memory backend
│       └── schemas.sql        # PostgreSQL schema
├── cli.py                     # Command-line tool
├── tests/                     # Test suite
│   ├── test_clean.py
│   ├── test_health.py
│   ├── test_resolver.py
│   └── test_sentiment.py
├── docs/
│   └── DATABASE_INTEGRATION_GUIDE.md  # PostgreSQL setup guide
├── .env                       # Configuration
├── .env.example               # Configuration template
├── requirements.txt           # Python dependencies
├── verify_database.py         # Database verification script
└── README.md                  # This file
```

### Adding New Features

1. **New API Client**: Add to `app/services/`
2. **New NLP Feature**: Add to `app/nlp/`
3. **New Endpoint**: Add to `app/main.py`
4. **New Tests**: Add to `tests/`

### Running Tests

```bash
# All tests
pytest tests/ -v

# With coverage
pytest tests/ --cov=app

# Specific test
pytest tests/test_sentiment.py::TestSentimentAnalysis::test_positive_sentiment -v

# Skip slow tests
pytest tests/ -v -m "not slow"
```

## Deployment

### Local Development
Already covered in Quick Start!

### Production

1. Use PostgreSQL for persistence:
```bash
USE_POSTGRES=true
DATABASE_URL=your_production_db_url
```

2. Configure proper logging:
```bash
LOG_LEVEL=WARNING
```

3. Secure your API:
- Add authentication middleware
- Configure CORS properly
- Use HTTPS in production

4. Scale horizontally:
- Run multiple uvicorn workers
- Use load balancer
- Share PostgreSQL instance

## Troubleshooting

**Issue**: Import errors when running tests
```bash
# Solution: Install in development mode
pip install -e .
```

**Issue**: "Module not found" errors
```bash
# Solution: Add to PYTHONPATH
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
```

**Issue**: PostgreSQL connection fails
```bash
# Solution: Check if using in-memory mode (default)
# Or see docs/DATABASE_INTEGRATION_GUIDE.md for PostgreSQL setup
# Or run: python verify_database.py to diagnose the issue
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass: `pytest tests/ -v`
5. Submit a pull request

## License

MIT License - see LICENSE file for details.

## Roadmap

- [ ] Implement Reddit OAuth and search
- [ ] Implement X API v2 integration
- [ ] Add StockTwits Firestream support
- [ ] Replace heuristic sentiment with FinBERT
- [ ] Add sentence-transformers for embeddings
- [ ] Implement similarity search
- [ ] Add time-series analysis
- [ ] Create Kubernetes deployment configs
- [ ] Add Grafana dashboards
- [ ] Implement webhook notifications

## Support

- **Issues**: [GitHub Issues](https://github.com/yourusername/sentiment-bot/issues)
- **Documentation**: See `/docs` endpoint when running
- **Tests**: Run `pytest tests/ -v` to verify installation
