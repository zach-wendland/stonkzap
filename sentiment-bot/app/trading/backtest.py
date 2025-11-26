"""
Backtesting engine for swing trading strategies.

Tests historical data to validate signal effectiveness before live trading.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional
import yfinance as yf
import numpy as np
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class TradeResult(BaseModel):
    """Result of a single backtest trade."""
    symbol: str
    entry_date: datetime
    entry_price: float
    exit_date: datetime
    exit_price: float
    exit_reason: str  # "stop_loss", "target_1", "target_2", "target_3", "timeout"
    gain_pct: float
    profit_dollars: int  # Assuming fixed position size
    is_win: bool


class BacktestReport(BaseModel):
    """Summary report of backtest results."""
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate_pct: float
    avg_win_pct: float
    avg_loss_pct: float
    avg_gain_pct: float
    total_profit: int
    largest_win: float
    largest_loss: float
    profit_factor: float  # Gross profit / gross loss
    sharpe_ratio: float  # Risk-adjusted returns
    max_drawdown_pct: float
    consecutive_losses: int
    consecutive_wins: int
    signal_type: str  # "reversal", "momentum", "catalyst"
    period: str


def get_historical_sentiment_proxy(
    symbol: str,
    date: datetime,
    signal_type: str = "momentum"
) -> float:
    """
    Get a proxy sentiment score for historical backtesting.

    In a real scenario, you'd have historical sentiment data stored.
    For now, use simple heuristics based on price action.

    Args:
        symbol: Stock symbol
        date: Date to evaluate
        signal_type: Type of signal to backtest

    Returns:
        Proxied sentiment polarity (0-1)
    """
    # This is a simplification. Real implementation would query historical sentiment DB
    # For backtest, we estimate sentiment based on price momentum
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(start=date - timedelta(days=30), end=date)

        if len(hist) < 5:
            return 0.5  # Neutral if not enough data

        # Price momentum = proxy for positive sentiment
        price_change = (hist['Close'].iloc[-1] - hist['Close'].iloc[0]) / hist['Close'].iloc[0]

        # Convert price change to sentiment proxy (-1 to 1)
        sentiment = np.clip(price_change * 2, -1, 1)

        # Add slight boost to momentum signals
        if signal_type == "momentum":
            sentiment += 0.2

        return max(0, min(1, (sentiment + 1) / 2))  # Scale to 0-1

    except Exception as e:
        logger.warning(f"Error getting historical sentiment proxy for {symbol}: {e}")
        return 0.5


def should_enter_trade(
    symbol: str,
    date: datetime,
    signal_type: str = "momentum",
    sentiment_threshold: float = 0.6
) -> bool:
    """
    Determine if a trade should be entered based on historical signals.

    Args:
        symbol: Stock symbol
        date: Entry date
        signal_type: Type of signal
        sentiment_threshold: Minimum sentiment to enter

    Returns:
        True if trade should enter
    """
    sentiment = get_historical_sentiment_proxy(symbol, date, signal_type)
    return sentiment >= sentiment_threshold


def backtest_strategy(
    symbols: List[str],
    strategy_name: str = "momentum",
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    entry_price: Optional[float] = None,
    stop_loss_pct: float = 0.10,  # 10% stop
    target_1_pct: float = 0.20,  # 20% profit
    target_2_pct: float = 0.50,  # 50% profit
    target_3_pct: float = 1.00,  # 100% profit
    hold_days: int = 30,
    position_size: int = 100  # shares per trade
) -> Dict:
    """
    Backtest a trading strategy on historical data.

    Args:
        symbols: List of stock symbols to test
        strategy_name: Name of strategy ("momentum", "reversal", "catalyst")
        start_date: Backtest start date (defaults to 1 year ago)
        end_date: Backtest end date (defaults to today)
        entry_price: Fixed entry price per share (if None, use daily open)
        stop_loss_pct: Stop loss percentage (default 10%)
        target_1_pct: First profit target percentage
        target_2_pct: Second profit target percentage
        target_3_pct: Third profit target percentage
        hold_days: Max days to hold a position
        position_size: Number of shares per trade

    Returns:
        BacktestReport dict with detailed results
    """
    if start_date is None:
        start_date = datetime.utcnow() - timedelta(days=365)
    if end_date is None:
        end_date = datetime.utcnow()

    logger.info(
        f"Backtest: {strategy_name} strategy on {len(symbols)} symbols "
        f"from {start_date.date()} to {end_date.date()}"
    )

    all_trades: List[TradeResult] = []

    for symbol in symbols:
        try:
            # Fetch historical data
            ticker = yf.Ticker(symbol)
            hist = ticker.history(start=start_date - timedelta(days=30), end=end_date)

            if hist.empty or len(hist) < hold_days:
                logger.warning(f"Insufficient data for {symbol}")
                continue

            # Simulate entries at various dates
            for i, (entry_date, row) in enumerate(hist.iterrows()):
                # Skip if we don't have enough future data for hold period
                if i + hold_days >= len(hist):
                    break

                # Check if entry signal would have triggered
                if not should_enter_trade(symbol, entry_date, strategy_name):
                    continue

                # Entry price
                entry = entry_price or row['Open']
                if entry_price is None or entry_price == 0:
                    entry = row['Close']

                stop_loss = entry * (1 - stop_loss_pct)
                target_1 = entry * (1 + target_1_pct)
                target_2 = entry * (1 + target_2_pct)
                target_3 = entry * (1 + target_3_pct)

                # Simulate trade over hold period
                exit_price = entry
                exit_date = entry_date
                exit_reason = "timeout"

                for j in range(1, hold_days + 1):
                    if i + j >= len(hist):
                        break

                    future_date = hist.index[i + j]
                    future_high = hist.loc[future_date, 'High']
                    future_low = hist.loc[future_date, 'Low']
                    future_close = hist.loc[future_date, 'Close']

                    # Check stop loss hit
                    if future_low <= stop_loss:
                        exit_price = stop_loss
                        exit_date = future_date
                        exit_reason = "stop_loss"
                        break

                    # Check targets hit (prioritize higher targets)
                    if future_high >= target_3:
                        exit_price = target_3
                        exit_date = future_date
                        exit_reason = "target_3"
                        break
                    elif future_high >= target_2:
                        exit_price = target_2
                        exit_date = future_date
                        exit_reason = "target_2"
                        break
                    elif future_high >= target_1:
                        exit_price = target_1
                        exit_date = future_date
                        exit_reason = "target_1"
                        break

                    # On last day, close at market
                    if j == hold_days - 1:
                        exit_price = future_close
                        exit_date = future_date
                        exit_reason = "timeout"

                # Record trade
                gain_pct = ((exit_price - entry) / entry)
                profit = int((exit_price - entry) * position_size)
                is_win = profit > 0

                trade = TradeResult(
                    symbol=symbol,
                    entry_date=entry_date,
                    entry_price=entry,
                    exit_date=exit_date,
                    exit_price=exit_price,
                    exit_reason=exit_reason,
                    gain_pct=gain_pct,
                    profit_dollars=profit,
                    is_win=is_win
                )

                all_trades.append(trade)

        except Exception as e:
            logger.warning(f"Error backtesting {symbol}: {e}")
            continue

    # Calculate statistics
    if not all_trades:
        logger.warning("No trades generated in backtest")
        return {
            "error": "No trades generated with current parameters",
            "symbol_count": len(symbols),
            "total_trades": 0
        }

    winning_trades = [t for t in all_trades if t.is_win]
    losing_trades = [t for t in all_trades if not t.is_win]

    win_count = len(winning_trades)
    loss_count = len(losing_trades)
    total_count = len(all_trades)

    avg_win = np.mean([t.gain_pct for t in winning_trades]) if winning_trades else 0
    avg_loss = np.mean([t.gain_pct for t in losing_trades]) if losing_trades else 0
    avg_gain = np.mean([t.gain_pct for t in all_trades])

    total_profit = sum(t.profit_dollars for t in all_trades)
    gross_profit = sum(t.profit_dollars for t in winning_trades) if winning_trades else 0
    gross_loss = abs(sum(t.profit_dollars for t in losing_trades)) if losing_trades else 0

    profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0

    # Sharpe ratio (simplified)
    returns = [t.gain_pct for t in all_trades]
    if len(returns) > 1:
        sharpe = (np.mean(returns) / np.std(returns)) * np.sqrt(252) if np.std(returns) > 0 else 0
    else:
        sharpe = 0

    # Max drawdown
    cumulative_pnl = np.cumsum([t.profit_dollars for t in all_trades])
    running_max = np.maximum.accumulate(cumulative_pnl)
    drawdown = (cumulative_pnl - running_max) / np.abs(running_max)
    max_drawdown = np.min(drawdown) if len(drawdown) > 0 else 0

    # Consecutive wins/losses
    max_consecutive_wins = 0
    max_consecutive_losses = 0
    current_wins = 0
    current_losses = 0

    for trade in all_trades:
        if trade.is_win:
            current_wins += 1
            current_losses = 0
            max_consecutive_wins = max(max_consecutive_wins, current_wins)
        else:
            current_losses += 1
            current_wins = 0
            max_consecutive_losses = max(max_consecutive_losses, current_losses)

    return {
        "total_trades": total_count,
        "winning_trades": win_count,
        "losing_trades": loss_count,
        "win_rate_pct": (win_count / total_count * 100) if total_count > 0 else 0,
        "avg_win_pct": avg_win * 100,
        "avg_loss_pct": avg_loss * 100,
        "avg_gain_pct": avg_gain * 100,
        "total_profit": total_profit,
        "largest_win": max([t.gain_pct for t in winning_trades]) * 100 if winning_trades else 0,
        "largest_loss": min([t.gain_pct for t in losing_trades]) * 100 if losing_trades else 0,
        "profit_factor": round(profit_factor, 2),
        "sharpe_ratio": round(sharpe, 2),
        "max_drawdown_pct": max_drawdown * 100,
        "consecutive_wins": max_consecutive_wins,
        "consecutive_losses": max_consecutive_losses,
        "signal_type": strategy_name,
        "period": f"{start_date.date()} to {end_date.date()}",
        "trades": [
            {
                "symbol": t.symbol,
                "entry": t.entry_date.strftime("%Y-%m-%d"),
                "exit": t.exit_date.strftime("%Y-%m-%d"),
                "entry_price": round(t.entry_price, 2),
                "exit_price": round(t.exit_price, 2),
                "gain": f"{t.gain_pct * 100:.1f}%",
                "profit": t.profit_dollars,
                "exit_reason": t.exit_reason
            }
            for t in all_trades[:50]  # Show first 50 trades
        ]
    }
