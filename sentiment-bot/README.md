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
