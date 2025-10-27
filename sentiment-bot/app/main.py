from fastapi import FastAPI, Query, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import time
from collections import defaultdict
from datetime import datetime, timedelta
from app.orchestration.tasks import aggregate_social, healthcheck
from app.config import get_settings
from app.logging_config import setup_logging, get_logger

# Initialize settings and logging
settings = get_settings()
setup_logging(settings.log_level)
logger = get_logger(__name__)

app = FastAPI(
    title="Sentiment Bot API",
    description="Social media sentiment analysis for financial instruments",
    version="1.0.0"
)

# Simple in-memory rate limiter
rate_limit_store = defaultdict(list)

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Simple rate limiting middleware."""
    if not settings.rate_limit_enabled:
        return await call_next(request)

    client_ip = request.client.host
    now = datetime.now()

    # Clean old requests
    rate_limit_store[client_ip] = [
        req_time for req_time in rate_limit_store[client_ip]
        if now - req_time < timedelta(seconds=settings.rate_limit_window)
    ]

    # Check rate limit
    if len(rate_limit_store[client_ip]) >= settings.rate_limit_requests:
        logger.warning(f"Rate limit exceeded for {client_ip}")
        return JSONResponse(
            status_code=429,
            content={
                "error": "Rate limit exceeded",
                "retry_after": settings.rate_limit_window
            }
        )

    # Add current request
    rate_limit_store[client_ip].append(now)

    return await call_next(request)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    """Log startup information."""
    logger.info("Starting Sentiment Bot API")
    logger.info(f"Dry run mode: {settings.dry_run}")
    logger.info(f"Rate limiting: {settings.rate_limit_enabled}")
    logger.info(f"Allow unofficial sources: {settings.allow_unofficial}")

@app.on_event("shutdown")
async def shutdown_event():
    """Log shutdown information."""
    logger.info("Shutting down Sentiment Bot API")

@app.get("/healthz")
def health_check():
    """Health check endpoint."""
    logger.debug("Health check requested")
    return healthcheck()

@app.get("/query")
def query_sentiment(
    symbol: str = Query(..., min_length=1, max_length=10, description="Stock symbol or company name"),
    window: str = Query("24h", regex="^[0-9]+[hd]$", description="Time window (e.g., 24h, 7d)")
):
    """Query sentiment for a given symbol."""
    logger.info(f"Sentiment query: symbol={symbol}, window={window}")

    try:
        result = aggregate_social(symbol.upper(), window)
        logger.info(f"Query completed: {result.get('count', 0)} posts processed")
        return result
    except ValueError as e:
        logger.error(f"Validation error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except ConnectionError as e:
        logger.error(f"Database connection error: {str(e)}")
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")
    except Exception as e:
        logger.exception(f"Unexpected error processing query for {symbol}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/")
def root():
    """API root with documentation."""
    logger.debug("Root endpoint accessed")
    return {
        "service": "Sentiment Bot API",
        "version": "1.0.0",
        "endpoints": {
            "health": "/healthz",
            "query": "/query?symbol=AAPL&window=24h",
            "docs": "/docs"
        },
        "documentation": "/docs"
    }
