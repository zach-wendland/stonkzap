import logging
import logging.config
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from app.orchestration.tasks import aggregate_social, healthcheck
from app.config import get_settings
from app.trading.scanner import scan_market, get_stock_list
from app.trading.backtest import backtest_strategy
from app.database import init_db
from app.routers import auth, portfolio, trades

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

# CORS - Allow frontend domain
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",      # React dev server
        "http://localhost:5173",       # Vite dev server
        "http://localhost:8000",       # Same domain (testing)
        "https://yourdomain.com",      # Production (update with real domain)
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router)
app.include_router(portfolio.router)
app.include_router(trades.router)

@app.on_event("startup")
async def startup():
    """Initialize database and log startup."""
    try:
        init_db()
        logger.info("Database initialized")
    except Exception as e:
        logger.error(f"Database init failed: {e}")
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


@app.get("/backtest")
def backtest_signals(
    strategy: str = Query("momentum", regex="^(momentum|reversal|catalyst)$", description="Strategy type"),
    days_back: int = Query(365, ge=30, le=1460, description="Days of historical data to backtest (30-4yr)")
):
    """
    Backtest a trading strategy on historical data.

    Runs signal strategy against past price/sentiment data to validate effectiveness.
    Shows win rate, profit factor, and risk/reward metrics.

    Strategies:
    - **momentum**: Buy stocks up 20% with positive sentiment (trend continuation)
    - **reversal**: Buy stocks down 20% with positive sentiment (contrarian)
    - **catalyst**: Buy stocks with positive sentiment but flat price (early entry)

    Returns:
    - Win rate percentage
    - Average win/loss per trade
    - Profit factor (gross profit / gross loss)
    - Sharpe ratio (risk-adjusted returns)
    - Max drawdown
    - Detailed trade log
    """
    logger.info(f"Backtest requested: strategy={strategy}, days_back={days_back}")

    try:
        from datetime import datetime, timedelta

        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days_back)

        # Get curated stock list for testing
        symbols = get_stock_list()[:100]  # Use first 100 for speed

        results = backtest_strategy(
            symbols=symbols,
            strategy_name=strategy,
            start_date=start_date,
            end_date=end_date,
            hold_days=30,
            position_size=100  # Shares per trade
        )

        logger.info(f"Backtest complete: {results.get('total_trades', 0)} trades")

        return {
            "strategy": strategy,
            "period": results.get("period", "N/A"),
            "statistics": {
                "total_trades": results.get("total_trades", 0),
                "winning_trades": results.get("winning_trades", 0),
                "losing_trades": results.get("losing_trades", 0),
                "win_rate": f"{results.get('win_rate_pct', 0):.1f}%",
                "avg_win": f"{results.get('avg_win_pct', 0):.1f}%",
                "avg_loss": f"{results.get('avg_loss_pct', 0):.1f}%",
                "avg_gain": f"{results.get('avg_gain_pct', 0):.1f}%",
                "total_profit": f"${results.get('total_profit', 0):,}",
                "largest_win": f"{results.get('largest_win', 0):.1f}%",
                "largest_loss": f"{results.get('largest_loss', 0):.1f}%",
                "profit_factor": results.get("profit_factor", 0),
                "sharpe_ratio": results.get("sharpe_ratio", 0),
                "max_drawdown": f"{results.get('max_drawdown_pct', 0):.1f}%",
                "consecutive_wins": results.get("consecutive_wins", 0),
                "consecutive_losses": results.get("consecutive_losses", 0)
            },
            "interpretation": _interpret_backtest(results),
            "edge_detected": _has_statistical_edge(results),
            "recommendation": _get_recommendation(results),
            "sample_trades": results.get("trades", [])[:10]  # First 10 trades
        }

    except Exception as e:
        logger.error(f"Error running backtest: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to run backtest")


def _interpret_backtest(results: Dict) -> str:
    """Interpret backtest results for the user."""
    win_rate = results.get("win_rate_pct", 0)
    profit_factor = results.get("profit_factor", 0)
    total_trades = results.get("total_trades", 0)

    if total_trades < 10:
        return "Insufficient trades to draw conclusions."

    if win_rate > 55 and profit_factor > 2.0:
        return "Strong edge detected: High win rate + strong profit factor."
    elif win_rate > 50 and profit_factor > 1.5:
        return "Positive edge: Win rate and profit factor support trading."
    elif win_rate > 45 and profit_factor > 1.0:
        return "Marginal edge: Possible with strict risk management."
    else:
        return "No edge detected: Strategy not recommended for live trading."


def _has_statistical_edge(results: Dict) -> bool:
    """Check if results show statistical edge for trading."""
    win_rate = results.get("win_rate_pct", 0)
    profit_factor = results.get("profit_factor", 0)
    total_trades = results.get("total_trades", 0)

    # Minimum criteria for edge
    return (
        total_trades >= 10 and
        win_rate >= 45 and
        profit_factor >= 1.0
    )


def _get_recommendation(results: Dict) -> str:
    """Get recommendation based on backtest."""
    if not _has_statistical_edge(results):
        return (
            "Not recommended for live trading yet. "
            "Consider adjusting parameters or waiting for more data."
        )

    win_rate = results.get("win_rate_pct", 0)
    profit_factor = results.get("profit_factor", 0)

    if win_rate > 55 and profit_factor > 2.0:
        return (
            "Strong signal to trade! Backtest shows edge. "
            "Start with small position size and scale up."
        )
    elif profit_factor > 1.5:
        return (
            "Good signal. Backtest shows consistent edge. "
            "Trade with normal risk parameters."
        )
    else:
        return (
            "Marginal edge detected. Trade with caution. "
            "Reduce position size and use strict stops."
        )


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
            "backtest": "/backtest?strategy=momentum&days_back=365",
            "docs": "/docs",
            "redoc": "/redoc"
        }
    }
