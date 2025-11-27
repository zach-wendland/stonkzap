"""
Trade journal endpoints.
"""

import logging
from typing import List
from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from pydantic import BaseModel
from datetime import datetime

from app.models import Trade, User
from app.database import get_db
from app.auth import verify_token

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/trades", tags=["trades"])


class TradeCreate(BaseModel):
    """Create trade payload."""
    symbol: str
    company_name: str
    entry_date: datetime
    entry_price: float
    quantity: int
    exit_date: datetime
    exit_price: float
    exit_reason: str = "manual"
    conviction_score: float = None
    signal_type: str = None
    notes: str = None


class TradeResponse(BaseModel):
    """Trade response."""
    id: int
    symbol: str
    company_name: str
    entry_date: datetime
    entry_price: float
    quantity: int
    exit_date: datetime
    exit_price: float
    exit_reason: str
    gain_dollars: float
    gain_percent: float
    is_win: bool
    hold_days: int
    conviction_score: float = None
    signal_type: str = None
    notes: str = None

    class Config:
        from_attributes = True


class TradeStatistics(BaseModel):
    """Trade statistics."""
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate_pct: float
    total_profit: float
    avg_win: float
    avg_loss: float
    profit_factor: float
    avg_hold_days: float


def get_current_user(token: str = Query(None), db: Session = Depends(get_db)) -> User:
    """Extract current user from token."""
    if not token:
        raise HTTPException(status_code=401, detail="Missing token")
    token_data = verify_token(token)
    if not token_data:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = db.query(User).filter(User.id == token_data.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.post("/", response_model=TradeResponse)
def create_trade(
    trade: TradeCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Log a completed trade."""
    db_trade = Trade(
        user_id=user.id,
        symbol=trade.symbol,
        company_name=trade.company_name,
        entry_date=trade.entry_date,
        entry_price=trade.entry_price,
        quantity=trade.quantity,
        exit_date=trade.exit_date,
        exit_price=trade.exit_price,
        exit_reason=trade.exit_reason,
        conviction_score=trade.conviction_score,
        signal_type=trade.signal_type,
        notes=trade.notes
    )
    db.add(db_trade)
    db.commit()
    db.refresh(db_trade)
    logger.info(f"Trade logged: {db_trade.id} {trade.symbol}")
    return TradeResponse.from_orm(db_trade)


@router.get("/", response_model=List[TradeResponse])
def list_trades(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    symbol: str = Query(None),
    status: str = Query(None, regex="^(win|loss)$"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List trades with pagination and filters."""
    query = db.query(Trade).filter(Trade.user_id == user.id)

    if symbol:
        query = query.filter(Trade.symbol == symbol.upper())

    if status == "win":
        query = query.filter(Trade.gain_dollars > 0)
    elif status == "loss":
        query = query.filter(Trade.gain_dollars <= 0)

    total = query.count()
    trades = query.order_by(desc(Trade.entry_date)).offset((page - 1) * limit).limit(limit).all()

    return [TradeResponse.from_orm(t) for t in trades]


@router.get("/statistics", response_model=TradeStatistics)
def get_statistics(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get trade statistics."""
    trades = db.query(Trade).filter(Trade.user_id == user.id).all()

    if not trades:
        return TradeStatistics(
            total_trades=0, winning_trades=0, losing_trades=0,
            win_rate_pct=0, total_profit=0, avg_win=0,
            avg_loss=0, profit_factor=0, avg_hold_days=0
        )

    wins = [t for t in trades if t.is_win]
    losses = [t for t in trades if not t.is_win]

    total_profit = sum(t.gain_dollars for t in trades)
    avg_win = sum(t.gain_dollars for t in wins) / len(wins) if wins else 0
    avg_loss = sum(t.gain_dollars for t in losses) / len(losses) if losses else 1
    profit_factor = sum(t.gain_dollars for t in wins) / abs(sum(t.gain_dollars for t in losses)) if losses else 0

    return TradeStatistics(
        total_trades=len(trades),
        winning_trades=len(wins),
        losing_trades=len(losses),
        win_rate_pct=(len(wins) / len(trades) * 100) if trades else 0,
        total_profit=total_profit,
        avg_win=avg_win,
        avg_loss=avg_loss,
        profit_factor=profit_factor,
        avg_hold_days=sum(t.hold_days for t in trades) / len(trades) if trades else 0
    )


@router.get("/{trade_id}", response_model=TradeResponse)
def get_trade(
    trade_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a specific trade."""
    trade = db.query(Trade).filter(
        Trade.id == trade_id,
        Trade.user_id == user.id
    ).first()
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    return TradeResponse.from_orm(trade)
