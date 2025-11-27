"""
Portfolio management endpoints for positions.
"""

import logging
from typing import List
from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime

from app.models import Position, User
from app.database import get_db
from app.auth import verify_token

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/portfolio", tags=["portfolio"])


class PositionCreate(BaseModel):
    """Create position payload."""
    symbol: str
    company_name: str
    entry_price: float
    quantity: int
    stop_loss: float
    target_1: float
    target_2: float
    target_3: float
    conviction_score: float = None
    signal_type: str = None
    notes: str = None


class PositionUpdate(BaseModel):
    """Update position payload."""
    current_price: float = None
    notes: str = None


class PositionClose(BaseModel):
    """Close position payload."""
    closed_price: float
    closed_reason: str = "manual"  # manual, stop_loss, target_1, target_2, target_3


class PositionResponse(BaseModel):
    """Position response model."""
    id: int
    symbol: str
    company_name: str
    entry_price: float
    quantity: int
    stop_loss: float
    target_1: float
    target_2: float
    target_3: float
    current_price: float = None
    current_pnl_dollars: float = 0
    current_pnl_percent: float = 0
    status: str
    conviction_score: float = None
    signal_type: str = None
    notes: str = None
    opened_at: datetime
    closed_at: datetime = None
    closed_price: float = None

    class Config:
        from_attributes = True


def get_current_user(token: str = Query(None), db: Session = Depends(get_db)) -> User:
    """Extract and verify current user from token."""
    if not token:
        raise HTTPException(status_code=401, detail="Missing token")

    token_data = verify_token(token)
    if not token_data:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = db.query(User).filter(User.id == token_data.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return user


@router.post("/positions", response_model=PositionResponse)
def create_position(
    position: PositionCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Create a new trading position.

    Args:
        position: PositionCreate payload
        user: Current authenticated user
        db: Database session

    Returns:
        Created position
    """
    logger.info(f"Creating position for user {user.id}: {position.symbol}")

    try:
        db_position = Position(
            user_id=user.id,
            symbol=position.symbol,
            company_name=position.company_name,
            entry_price=position.entry_price,
            quantity=position.quantity,
            stop_loss=position.stop_loss,
            target_1=position.target_1,
            target_2=position.target_2,
            target_3=position.target_3,
            conviction_score=position.conviction_score,
            signal_type=position.signal_type,
            notes=position.notes,
            status="open"
        )

        db.add(db_position)
        db.commit()
        db.refresh(db_position)

        logger.info(f"Position created: {db_position.id}")
        return PositionResponse.from_orm(db_position)

    except Exception as e:
        db.rollback()
        logger.error(f"Error creating position: {e}")
        raise HTTPException(status_code=500, detail="Failed to create position")


@router.get("/positions", response_model=List[PositionResponse])
def list_positions(
    status: str = Query("open", regex="^(open|closed|all)$"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    List positions for current user.

    Args:
        status: Filter by status (open, closed, all)
        user: Current user
        db: Database session

    Returns:
        List of positions
    """
    query = db.query(Position).filter(Position.user_id == user.id)

    if status != "all":
        query = query.filter(Position.status == status)

    positions = query.order_by(Position.opened_at.desc()).all()

    return [PositionResponse.from_orm(p) for p in positions]


@router.get("/positions/{position_id}", response_model=PositionResponse)
def get_position(
    position_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a specific position."""
    position = db.query(Position).filter(
        Position.id == position_id,
        Position.user_id == user.id
    ).first()

    if not position:
        raise HTTPException(status_code=404, detail="Position not found")

    return PositionResponse.from_orm(position)


@router.put("/positions/{position_id}", response_model=PositionResponse)
def update_position(
    position_id: int,
    update: PositionUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a position."""
    position = db.query(Position).filter(
        Position.id == position_id,
        Position.user_id == user.id
    ).first()

    if not position:
        raise HTTPException(status_code=404, detail="Position not found")

    if update.current_price is not None:
        position.current_price = update.current_price
    if update.notes is not None:
        position.notes = update.notes

    db.commit()
    db.refresh(position)

    return PositionResponse.from_orm(position)


@router.post("/positions/{position_id}/close", response_model=PositionResponse)
def close_position(
    position_id: int,
    close_data: PositionClose,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Close an open position."""
    position = db.query(Position).filter(
        Position.id == position_id,
        Position.user_id == user.id,
        Position.status == "open"
    ).first()

    if not position:
        raise HTTPException(status_code=404, detail="Position not found or already closed")

    position.status = "closed"
    position.closed_price = close_data.closed_price
    position.closed_reason = close_data.closed_reason
    position.closed_at = datetime.utcnow()

    db.commit()
    db.refresh(position)

    logger.info(f"Position closed: {position.id} at {close_data.closed_price}")

    return PositionResponse.from_orm(position)


@router.delete("/positions/{position_id}")
def delete_position(
    position_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a position (soft delete via closing)."""
    position = db.query(Position).filter(
        Position.id == position_id,
        Position.user_id == user.id
    ).first()

    if not position:
        raise HTTPException(status_code=404, detail="Position not found")

    db.delete(position)
    db.commit()

    logger.info(f"Position deleted: {position_id}")

    return {"message": "Position deleted"}
