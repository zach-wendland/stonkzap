"""
Authentication routes for user login/registration.
"""

import logging
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.models import User
from app.auth import (
    UserCreate, UserLogin, Token, TokenData, UserResponse,
    hash_password, verify_password, create_access_token, create_refresh_token, verify_token
)
from app.database import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/register", response_model=UserResponse)
def register(user: UserCreate, db: Session = Depends(get_db)):
    """
    Register a new user account.

    Args:
        user: UserCreate with email and password

    Returns:
        UserResponse with created user info
    """
    logger.info(f"Registration attempt for {user.email}")

    try:
        # Check if user exists
        existing = db.query(User).filter(User.email == user.email).first()
        if existing:
            logger.warning(f"Registration failed: {user.email} already exists")
            raise HTTPException(status_code=400, detail="Email already registered")

        # Hash password
        hashed_pwd = hash_password(user.password)

        # Create user
        db_user = User(email=user.email, password_hash=hashed_pwd)
        db.add(db_user)
        db.commit()
        db.refresh(db_user)

        logger.info(f"User registered: {user.email}")
        return UserResponse.from_orm(db_user)

    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Email already registered")
    except Exception as e:
        db.rollback()
        logger.error(f"Registration error: {e}")
        raise HTTPException(status_code=500, detail="Registration failed")


@router.post("/login", response_model=Token)
def login(credentials: UserLogin, db: Session = Depends(get_db)):
    """
    Login user and return JWT tokens.

    Args:
        credentials: UserLogin with email and password

    Returns:
        Token with access_token and refresh_token
    """
    logger.info(f"Login attempt for {credentials.email}")

    # Find user
    user = db.query(User).filter(User.email == credentials.email).first()
    if not user:
        logger.warning(f"Login failed: user not found {credentials.email}")
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Verify password
    if not verify_password(credentials.password, user.password_hash):
        logger.warning(f"Login failed: invalid password for {credentials.email}")
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Generate tokens
    access_token = create_access_token(user.id, user.email)
    refresh_token = create_refresh_token(user.id, user.email)

    logger.info(f"User logged in: {credentials.email}")

    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer"
    )


@router.post("/refresh", response_model=Token)
def refresh(refresh_token: str):
    """
    Refresh access token using refresh token.

    Args:
        refresh_token: Valid refresh token

    Returns:
        Token with new access_token
    """
    # Verify refresh token
    token_data = verify_token(refresh_token)
    if not token_data:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    # Generate new access token
    access_token = create_access_token(token_data.user_id, token_data.email)

    logger.info(f"Token refreshed for user {token_data.user_id}")

    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer"
    )


@router.get("/me", response_model=UserResponse)
def get_current_user(token: str = None, db: Session = Depends(get_db)):
    """
    Get current user info from token.

    Args:
        token: JWT access token (from Authorization header)
        db: Database session

    Returns:
        Current user info
    """
    if not token:
        raise HTTPException(status_code=401, detail="Missing token")

    # Verify token
    token_data = verify_token(token)
    if not token_data:
        raise HTTPException(status_code=401, detail="Invalid token")

    # Get user
    user = db.query(User).filter(User.id == token_data.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return UserResponse.from_orm(user)
