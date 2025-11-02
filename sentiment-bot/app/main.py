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
    """
    Initialize application on startup.

    THEORY OF MIND:
    You want the app to fail fast if there's a problem.
    Better to crash at startup than serve bad requests!
    """
    logger.info("Starting Sentiment Bot API")
    logger.info(f"Dry run mode: {settings.dry_run}")
    logger.info(f"Rate limiting: {settings.rate_limit_enabled}")
    logger.info(f"Allow unofficial sources: {settings.allow_unofficial}")

    # Initialize database pool if PostgreSQL is enabled
    if settings.use_postgres:
        try:
            from app.storage.db_pool import initialize_pool
            from app.storage.migrations import run_migrations

            logger.info("PostgreSQL enabled - initializing connection pool...")

            # Run any pending migrations
            if run_migrations(settings.database_url):
                logger.info("✓ Database migrations complete")
            else:
                logger.warning("⚠ Migration issues detected - check logs")

            # Initialize the connection pool
            pool = initialize_pool()
            if pool and pool.health_check():
                logger.info("✓ Database pool healthy and ready")
            else:
                logger.error("✗ Database pool health check failed")

        except Exception as e:
            logger.error(f"✗ Database initialization failed: {e}")
            logger.info("Continuing with in-memory storage as fallback")
    else:
        logger.info("Using in-memory storage (no database)")

@app.on_event("shutdown")
async def shutdown_event():
    """
    Cleanup on shutdown.

    WHAT THIS DOES:
    - Closes database connections gracefully
    - Prevents connection leaks
    - Allows time for in-flight requests
    """
    logger.info("Shutting down Sentiment Bot API")

    # Close database pool if it was initialized
    if settings.use_postgres:
        try:
            from app.storage.db_pool import close_pool
            close_pool()
            logger.info("Database pool closed")
        except Exception as e:
            logger.error(f"Error closing database pool: {e}")

@app.get("/healthz")
def health_check():
    """
    Basic health check endpoint.

    Returns application status without dependencies.
    """
    logger.debug("Health check requested")
    return healthcheck()

@app.get("/healthz/db")
def database_health_check():
    """
    Database-specific health check.

    WHAT THIS CHECKS:
    - Is PostgreSQL enabled?
    - Can we connect to the database?
    - Is the connection pool healthy?
    - What's the pool utilization?

    THEORY OF MIND:
    You want to monitor database health separately because:
    - Database issues are common in production
    - Need to know pool utilization before it's exhausted
    - Monitoring systems can alert on specific issues
    - Helps diagnose "why is it slow?" questions
    """
    if not settings.use_postgres:
        return {
            "status": "not_applicable",
            "backend": "in_memory",
            "message": "PostgreSQL not enabled - using in-memory storage"
        }

    try:
        from app.storage.db_pool import get_pool
        import time

        pool = get_pool()

        # Time a simple query
        start = time.time()
        is_healthy = pool.health_check()
        query_time_ms = (time.time() - start) * 1000

        if is_healthy:
            stats = pool.get_stats()
            return {
                "status": "healthy",
                "backend": "postgresql",
                "query_time_ms": round(query_time_ms, 2),
                "pool": stats
            }
        else:
            return {
                "status": "unhealthy",
                "backend": "postgresql",
                "message": "Database health check failed"
            }

    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return {
            "status": "error",
            "backend": "postgresql",
            "error": str(e)
        }

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
