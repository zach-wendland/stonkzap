import logging
import logging.config
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from app.orchestration.tasks import aggregate_social, healthcheck
from app.config import get_settings
from app.trading.scanner import scan_market

# Configure logging
def _configure_logging():
    """Configure structured logging for the application."""
    logging_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "standard": {
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            },
            "detailed": {
                "format": "%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s"
            }
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "standard",
                "level": "INFO"
            }
        },
        "root": {
            "level": "INFO",
            "handlers": ["console"]
        },
        "loggers": {
            "app": {
                "level": "DEBUG",
                "handlers": ["console"],
                "propagate": False
            }
        }
    }
    logging.config.dictConfig(logging_config)

_configure_logging()
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Sentiment Bot API",
    description="Social media sentiment analysis for financial instruments",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup():
    """Log startup."""
    logger.info("Sentiment Bot API starting up")

@app.on_event("shutdown")
async def shutdown():
    """Log shutdown."""
    logger.info("Sentiment Bot API shutting down")

@app.get("/healthz")
def health_check():
    """Health check endpoint."""
    try:
        result = healthcheck()
        return result
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail="Service unhealthy")

@app.get("/query")
def query_sentiment(
    symbol: str = Query(..., min_length=1, max_length=10, description="Stock symbol or company name"),
    window: str = Query("24h", regex="^[0-9]+[hd]$", description="Time window (e.g., 24h, 7d)")
):
    """
    Query sentiment for a stock symbol across multiple social media sources.

    Returns aggregated sentiment scores from X, Reddit, StockTwits, and Discord.
    """
    logger.info(f"Received query for symbol={symbol}, window={window}")

    try:
        result = aggregate_social(symbol.upper(), window)
        logger.info(f"Successfully processed query for {symbol}")
        return result
    except ValueError as e:
        logger.warning(f"Invalid query for {symbol}: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid input: {e}")
    except Exception as e:
        logger.error(f"Error processing query for {symbol}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to process query")

@app.get("/scan")
async def scan_opportunities(
    min_conviction: float = Query(5.0, ge=0, le=10, description="Minimum conviction score (0-10)"),
    max_results: int = Query(20, ge=1, le=50, description="Max opportunities to return")
):
    """
    Scan market for swing trading opportunities using sentiment/price divergence.

    Returns ranked list of stocks with high potential for swing trades.
    Focuses on NYSE/NASDAQ with $2K max loss per position.

    Scoring based on:
    - Sentiment/price divergence (contrarian setups)
    - Momentum confirmation (trend continuation)
    - Emerging catalysts (early entry before move)

    Each opportunity includes:
    - Entry price and position size ($2K max loss)
    - Stop loss (-10%) and profit targets (+20%, +50%, +100%)
    - Risk/reward ratio
    - Conviction score (5+/10 recommended)
    """
    logger.info(f"Received scan request: min_conviction={min_conviction}, max_results={max_results}")

    try:
        opportunities = await scan_market(
            min_conviction=min_conviction,
            max_results=max_results
        )

        logger.info(f"Scan returned {len(opportunities)} opportunities")

        return {
            "timestamp": aggregate_social.__doc__,  # Use current time
            "scan_parameters": {
                "min_conviction": min_conviction,
                "max_results": max_results,
                "max_loss_per_position": 2000,
                "exchange": ["NYSE", "NASDAQ"]
            },
            "opportunities": [
                {
                    "symbol": opp.symbol,
                    "company_name": opp.company_name,
                    "conviction_score": round(opp.conviction_score, 2),
                    "signal_type": opp.signal_type,
                    "reason": opp.divergence_reason,
                    "sentiment": {
                        "polarity": round(opp.sentiment_polarity, 3),
                        "confidence": round(opp.sentiment_confidence, 3)
                    },
                    "price_action": {
                        "current": round(opp.entry_price, 2),
                        "change_7d": f"{opp.price_change_7d:.1f}%",
                        "change_30d": f"{opp.price_change_30d:.1f}%"
                    },
                    "trade_setup": {
                        "entry": round(opp.entry_price, 2),
                        "stop_loss": round(opp.stop_loss, 2),
                        "target_1": f"{round(opp.target_1, 2)} (+20%)",
                        "target_2": f"{round(opp.target_2, 2)} (+50%)",
                        "target_3": f"{round(opp.target_3, 2)} (+100%)",
                        "position_size": f"${opp.position_size_dollars}",
                        "risk_reward_ratio": round(opp.risk_reward_ratio, 2)
                    }
                }
                for opp in opportunities
            ]
        }

    except Exception as e:
        logger.error(f"Error scanning market: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to scan market")


@app.get("/")
def root():
    """Root endpoint - service information."""
    return {
        "service": "Sentiment Bot API - Swing Trading Edition",
        "version": "1.0.0",
        "description": "Social media sentiment analysis + stock scanner for swing traders",
        "endpoints": {
            "health": "/healthz",
            "query": "/query?symbol=AAPL&window=24h",
            "scan": "/scan?min_conviction=5&max_results=20",
            "docs": "/docs",
            "redoc": "/redoc"
        }
    }
