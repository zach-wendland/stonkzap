"""
Database models for sentiment bot.

Uses SQLAlchemy ORM for PostgreSQL with SQLAlchemy 2.0 style.
"""

from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, ForeignKey, Enum, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

Base = declarative_base()


class User(Base):
    """User account model."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    positions = relationship("Position", back_populates="user", cascade="all, delete-orphan")
    trades = relationship("Trade", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User(id={self.id}, email={self.email})>"


class Position(Base):
    """Open trading position."""
    __tablename__ = "positions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    symbol = Column(String, index=True, nullable=False)
    company_name = Column(String)
    entry_price = Column(Float, nullable=False)
    quantity = Column(Integer, nullable=False)
    stop_loss = Column(Float, nullable=False)
    target_1 = Column(Float)
    target_2 = Column(Float)
    target_3 = Column(Float)
    current_price = Column(Float)  # Updated periodically
    status = Column(String, default="open")  # open, closed
    conviction_score = Column(Float)
    signal_type = Column(String)  # momentum, reversal, catalyst
    notes = Column(Text)
    opened_at = Column(DateTime, default=datetime.utcnow)
    closed_at = Column(DateTime)
    closed_price = Column(Float)
    closed_reason = Column(String)  # stop_loss, target_1, target_2, target_3, manual

    # Relationships
    user = relationship("User", back_populates="positions")

    def __repr__(self):
        return f"<Position(id={self.id}, symbol={self.symbol}, status={self.status})>"

    @property
    def current_pnl_dollars(self) -> float:
        if not self.current_price or self.status == "closed":
            return 0
        return (self.current_price - self.entry_price) * self.quantity

    @property
    def current_pnl_percent(self) -> float:
        if not self.current_price or self.entry_price == 0:
            return 0
        return ((self.current_price - self.entry_price) / self.entry_price) * 100


class Trade(Base):
    """Completed trade in journal."""
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    symbol = Column(String, index=True, nullable=False)
    company_name = Column(String)
    entry_date = Column(DateTime, nullable=False, index=True)
    entry_price = Column(Float, nullable=False)
    quantity = Column(Integer, nullable=False)
    exit_date = Column(DateTime, nullable=False)
    exit_price = Column(Float, nullable=False)
    exit_reason = Column(String)  # stop_loss, target_1, target_2, target_3, manual
    conviction_score = Column(Float)
    signal_type = Column(String)  # momentum, reversal, catalyst
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="trades")

    def __repr__(self):
        return f"<Trade(id={self.id}, symbol={self.symbol})>"

    @property
    def gain_dollars(self) -> float:
        return (self.exit_price - self.entry_price) * self.quantity

    @property
    def gain_percent(self) -> float:
        if self.entry_price == 0:
            return 0
        return ((self.exit_price - self.entry_price) / self.entry_price) * 100

    @property
    def is_win(self) -> bool:
        return self.gain_dollars > 0

    @property
    def hold_days(self) -> int:
        return (self.exit_date - self.entry_date).days
