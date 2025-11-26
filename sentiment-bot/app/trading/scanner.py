"""
Stock market scanner for swing trading opportunities.

Identifies stocks with divergence between sentiment and price action.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import yfinance as yf
import numpy as np
from pydantic import BaseModel

from app.orchestration.tasks import aggregate_social
from app.services.resolver import resolve

logger = logging.getLogger(__name__)


class PriceData(BaseModel):
    """Historical price data for a stock."""
    symbol: str
    current_price: float
    price_change_pct_7d: float  # % change over 7 days
    price_change_pct_30d: float  # % change over 30 days
    volume_7d_avg: float
    volume_30d_avg: float
    is_up_trend: bool  # True if price up in last 7 days
    retrieved_at: datetime


class OpportunityScore(BaseModel):
    """Swing trading opportunity with scoring."""
    symbol: str
    company_name: str
    conviction_score: float  # 0-10, higher = more confident
    sentiment_polarity: float  # -1 to 1
    sentiment_confidence: float  # 0-1
    price_change_7d: float  # % change
    price_change_30d: float  # % change
    divergence_reason: str  # Why we're excited about this
    entry_price: float
    stop_loss: float  # -10% from entry
    target_1: float  # +20%
    target_2: float  # +50%
    target_3: float  # +100%
    position_size_dollars: int  # How much to invest ($2K max loss)
    risk_reward_ratio: float  # Expected reward / risk
    signal_type: str  # "reversal", "momentum", "emerging_catalyst"


def get_stock_list(exchanges: List[str] = None) -> List[str]:
    """
    Get list of stocks to scan.

    Args:
        exchanges: List of exchanges (NYSE, NASDAQ)

    Returns:
        List of stock symbols
    """
    if exchanges is None:
        exchanges = ["NYSE", "NASDAQ"]

    # For MVP: Focus on liquid, high-volume stocks from major indices
    # In production, could load from SEC database

    sp500 = [
        "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA", "META", "AVGO",
        "ASML", "NFLX", "PYPL", "PEP", "COST", "AZO", "NKE", "MCD",
        "BA", "GS", "JPM", "BAC", "C", "WFC", "USB", "PNC",
        "AMD", "QCOM", "INTC", "MU", "ADBE", "CRM", "INTU", "SNPS",
        "UBER", "LYFT", "DASH", "ROKU", "SPOT", "ZM", "COIN",
        "ARKK", "MSTR", "MARA", "CLSK", "HUT", "RIOT", "COIN"
    ]

    # Add volatile NASDAQ stocks that swing more
    nasdaq_volatile = [
        "XPEV", "NIO", "LI", "BILI", "BIDU", "JD", "PDD", "TCEHY",
        "COIN", "RIOT", "MARA", "CLSK", "HUT", "MSTR",
        "LCID", "NPA", "CCIV", "QS", "PLUG", "BLNK", "CHK",
        "SPY", "QQQ", "IWM", "XLK", "XLC", "XLV", "XLF", "XLE"
    ]

    return list(set(sp500 + nasdaq_volatile))


def get_price_data(symbol: str, period: str = "3mo") -> Optional[PriceData]:
    """
    Fetch price data from yfinance.

    Args:
        symbol: Stock ticker
        period: Historical period (3mo, 6mo, 1y)

    Returns:
        PriceData object or None if fetch fails
    """
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period=period)

        if hist.empty:
            logger.warning(f"No price data for {symbol}")
            return None

        current_price = hist['Close'].iloc[-1]

        # Calculate price changes
        price_7d_ago = hist['Close'].iloc[-7] if len(hist) >= 7 else hist['Close'].iloc[0]
        price_30d_ago = hist['Close'].iloc[-30] if len(hist) >= 30 else hist['Close'].iloc[0]

        change_7d_pct = ((current_price - price_7d_ago) / price_7d_ago) * 100
        change_30d_pct = ((current_price - price_30d_ago) / price_30d_ago) * 100

        # Volume analysis
        volume_7d = hist['Volume'].tail(7).mean()
        volume_30d = hist['Volume'].tail(30).mean()

        is_up_trend = change_7d_pct > 0

        return PriceData(
            symbol=symbol,
            current_price=current_price,
            price_change_pct_7d=change_7d_pct,
            price_change_pct_30d=change_30d_pct,
            volume_7d_avg=volume_7d,
            volume_30d_avg=volume_30d,
            is_up_trend=is_up_trend,
            retrieved_at=datetime.utcnow()
        )
    except Exception as e:
        logger.warning(f"Failed to get price data for {symbol}: {e}")
        return None


def calculate_divergence_score(
    symbol: str,
    sentiment_polarity: float,
    sentiment_confidence: float,
    price_data: PriceData,
    max_loss_dollars: int = 2000
) -> Optional[OpportunityScore]:
    """
    Calculate swing trading opportunity score based on sentiment/price divergence.

    High scores indicate: sentiment and price misalignment likely to correct.

    Args:
        symbol: Stock symbol
        sentiment_polarity: -1 to 1 sentiment score
        sentiment_confidence: 0-1 confidence in sentiment
        price_data: Current price and trend data
        max_loss_dollars: Max loss per trade

    Returns:
        OpportunityScore if compelling opportunity exists
    """
    conviction_score = 0
    signal_type = None
    divergence_reason = ""

    # PATTERN 1: Sentiment Reversal (bearish price, bullish sentiment)
    # Stock down, but social sentiment positive = contrarian opportunity
    if price_data.price_change_30d < -15 and sentiment_polarity > 0.6:
        conviction_score += 6
        signal_type = "reversal"
        divergence_reason = (
            f"Bearish price action ({price_data.price_change_30d:.1f}% down 30d) "
            f"vs bullish sentiment ({sentiment_polarity:.2f}). Contrarian reversal candidate."
        )

    # PATTERN 2: Momentum Confirmation (bullish price + bullish sentiment)
    # Stock up AND sentiment positive = early momentum catch
    elif price_data.price_change_7d > 15 and sentiment_polarity > 0.65:
        conviction_score += 5
        signal_type = "momentum"
        divergence_reason = (
            f"Strong momentum: price up {price_data.price_change_7d:.1f}% (7d) "
            f"with positive sentiment ({sentiment_polarity:.2f}). Trend continuation play."
        )

    # PATTERN 3: Emerging Catalyst (sentiment spike with low price change)
    # Sentiment positive but stock hasn't run yet = early entry
    elif sentiment_polarity > 0.7 and -10 < price_data.price_change_7d < 10:
        conviction_score += 4
        signal_type = "emerging_catalyst"
        divergence_reason = (
            f"Sentiment catalyst detected (polarity {sentiment_polarity:.2f}) "
            f"but stock relatively flat. Early entry opportunity before institutional move."
        )

    else:
        # No strong divergence pattern
        return None

    # Boost score based on sentiment confidence
    conviction_score += (sentiment_confidence * 2)

    # Cap at 10
    conviction_score = min(10.0, conviction_score)

    # Only score opportunities with minimum conviction
    if conviction_score < 3.5:
        return None

    # Calculate position sizing based on Kelly Criterion
    # Assuming 50% win rate, 3:1 risk/reward (conservative)
    entry_price = price_data.current_price
    stop_loss = entry_price * 0.9  # 10% stop
    risk_per_share = entry_price - stop_loss
    position_size = int(max_loss_dollars / risk_per_share) if risk_per_share > 0 else 0

    if position_size <= 0:
        return None

    position_size_dollars = int(position_size * entry_price)

    # Targets
    target_1 = entry_price * 1.20  # +20%
    target_2 = entry_price * 1.50  # +50%
    target_3 = entry_price * 2.00  # +100%

    # Risk/reward: assume taking profit at +50% on half position
    expected_reward = (target_1 * 0.5 + target_2 * 0.5) - entry_price
    expected_risk = entry_price - stop_loss
    risk_reward = expected_reward / expected_risk if expected_risk > 0 else 0

    try:
        company_name = resolve(symbol).company_name
    except Exception:
        company_name = symbol

    return OpportunityScore(
        symbol=symbol,
        company_name=company_name,
        conviction_score=conviction_score,
        sentiment_polarity=sentiment_polarity,
        sentiment_confidence=sentiment_confidence,
        price_change_7d=price_data.price_change_pct_7d,
        price_change_30d=price_data.price_change_pct_30d,
        divergence_reason=divergence_reason,
        entry_price=entry_price,
        stop_loss=stop_loss,
        target_1=target_1,
        target_2=target_2,
        target_3=target_3,
        position_size_dollars=position_size_dollars,
        risk_reward_ratio=risk_reward,
        signal_type=signal_type or "unknown"
    )


async def scan_market(
    symbols: List[str] = None,
    min_conviction: float = 5.0,
    max_results: int = 20
) -> List[OpportunityScore]:
    """
    Scan market for swing trading opportunities.

    Args:
        symbols: Specific symbols to scan (defaults to curated list)
        min_conviction: Minimum conviction score (0-10)
        max_results: Max opportunities to return

    Returns:
        List of opportunities ranked by conviction score
    """
    if symbols is None:
        symbols = get_stock_list()

    logger.info(f"Scanning {len(symbols)} stocks for opportunities...")
    opportunities = []

    for i, symbol in enumerate(symbols):
        try:
            # Get sentiment
            sentiment_result = aggregate_social(symbol, window="7d")

            if sentiment_result.get("error") or sentiment_result.get("posts_processed", 0) < 5:
                logger.debug(f"Skipping {symbol}: insufficient data")
                continue

            sentiment_data = sentiment_result.get("sentiment", {})
            sentiment_polarity = sentiment_data.get("avg_polarity", 0)
            sentiment_confidence = sentiment_data.get("confidence", 0.3)

            # Get price data
            price_data = get_price_data(symbol)
            if not price_data:
                continue

            # Calculate opportunity score
            opportunity = calculate_divergence_score(
                symbol=symbol,
                sentiment_polarity=sentiment_polarity,
                sentiment_confidence=sentiment_confidence,
                price_data=price_data
            )

            if opportunity and opportunity.conviction_score >= min_conviction:
                opportunities.append(opportunity)
                logger.info(f"Found opportunity: {symbol} (conviction: {opportunity.conviction_score:.1f})")

        except Exception as e:
            logger.warning(f"Error scanning {symbol}: {e}")
            continue

        # Rate limiting - don't hammer APIs
        if i % 20 == 0:
            logger.info(f"Processed {i}/{len(symbols)} symbols...")

    # Sort by conviction score (highest first)
    opportunities.sort(key=lambda x: x.conviction_score, reverse=True)

    logger.info(f"Scan complete. Found {len(opportunities)} opportunities (top {max_results} returned)")

    return opportunities[:max_results]
