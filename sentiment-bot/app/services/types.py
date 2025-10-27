from pydantic import BaseModel
from typing import Literal, Optional, List
from datetime import datetime

class SocialPost(BaseModel):
    source: Literal["reddit", "x", "stocktwits", "yahoo_forum", "discord"]
    platform_id: str
    author_id: str
    author_handle: Optional[str] = None
    created_at: datetime
    text: str
    symbols: List[str] = []
    urls: List[str] = []
    lang: Optional[str] = None
    reply_to_id: Optional[str] = None
    repost_of_id: Optional[str] = None
    like_count: Optional[int] = None
    reply_count: Optional[int] = None
    repost_count: Optional[int] = None
    follower_count: Optional[int] = None
    permalink: Optional[str] = None

class SentimentScore(BaseModel):
    polarity: float
    subjectivity: float
    sarcasm_prob: float
    confidence: float
    model: str = "textblob"

class ResolvedInstrument(BaseModel):
    symbol: str
    cik: Optional[str] = None
    isin: Optional[str] = None
    figi: Optional[str] = None
    company_name: str
