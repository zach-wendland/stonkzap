from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from app.orchestration.tasks import aggregate_social, healthcheck
from app.config import get_settings

app = FastAPI(
    title="Sentiment Bot API",
    description="Social media sentiment analysis for financial instruments",
    version="1.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/healthz")
def health_check():
    return healthcheck()

@app.get("/query")
def query_sentiment(
    symbol: str = Query(..., min_length=1, description="Stock symbol or company name"),
    window: str = Query("24h", regex="^[0-9]+[hd]$", description="Time window (e.g., 24h, 7d)")
):
    try:
        result = aggregate_social(symbol.upper(), window)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
def root():
    return {
        "service": "Sentiment Bot API",
        "endpoints": {
            "health": "/healthz",
            "query": "/query?symbol=AAPL&window=24h"
        }
    }
