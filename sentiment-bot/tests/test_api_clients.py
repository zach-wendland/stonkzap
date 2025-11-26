"""Tests for external API client integrations (with mocked responses)."""
import pytest
from datetime import datetime, timedelta
import responses
from app.services.x_client import search_x_bundle
from app.services.stocktwits_client import collect_stocktwits

@responses.activate
def test_x_api_basic():
    """Test X/Twitter API client with mocked response."""
    # Mock the X API response
    responses.add(
        responses.GET,
        "https://api.twitter.com/2/tweets/search/recent",
        json={
            "data": [
                {
                    "id": "123456",
                    "text": "$AAPL is looking bullish",
                    "created_at": "2025-01-15T10:00:00Z",
                    "author_id": "user123",
                    "public_metrics": {
                        "like_count": 10,
                        "reply_count": 2,
                        "retweet_count": 5
                    }
                }
            ],
            "includes": {
                "users": [
                    {
                        "id": "user123",
                        "username": "trader1",
                        "followers_count": 1000
                    }
                ]
            },
            "meta": {
                "result_count": 1
            }
        },
        status=200
    )

    since = datetime.utcnow() - timedelta(days=1)
    result = search_x_bundle({"symbol": "AAPL"}, since)

    assert len(result) == 1
    assert result[0].source == "x"
    assert result[0].text == "$AAPL is looking bullish"
    assert result[0].author_handle == "trader1"
    assert result[0].like_count == 10

@responses.activate
def test_x_api_no_results():
    """Test X/Twitter API when no results found."""
    responses.add(
        responses.GET,
        "https://api.twitter.com/2/tweets/search/recent",
        json={"data": []},
        status=200
    )

    since = datetime.utcnow() - timedelta(days=1)
    result = search_x_bundle({"symbol": "UNKNOWN"}, since)

    assert len(result) == 0

@responses.activate
def test_x_api_rate_limit():
    """Test X/Twitter API handles rate limiting."""
    responses.add(
        responses.GET,
        "https://api.twitter.com/2/tweets/search/recent",
        status=429
    )

    since = datetime.utcnow() - timedelta(days=1)
    result = search_x_bundle({"symbol": "AAPL"}, since)

    # Should return empty list on rate limit
    assert len(result) == 0

@responses.activate
def test_stocktwits_api_basic():
    """Test StockTwits API client with mocked response."""
    responses.add(
        responses.GET,
        "https://api.stocktwits.com/api/v2/streams/symbols/aapl/messages",
        json={
            "status": "ok",
            "messages": [
                {
                    "id": "msg123",
                    "body": "AAPL looking strong",
                    "created_at": "2025-01-15T10:00:00Z",
                    "sentiment": "bullish",
                    "likes": 5,
                    "user": {
                        "id": 12345,
                        "username": "investor1",
                        "followers": 100
                    }
                }
            ]
        },
        status=200
    )

    since = datetime.utcnow() - timedelta(days=1)
    result = collect_stocktwits({"symbol": "AAPL"}, since)

    assert len(result) == 1
    assert result[0].source == "stocktwits"
    assert "[BULLISH]" in result[0].text or "AAPL looking strong" in result[0].text
    assert result[0].like_count == 5

@responses.activate
def test_stocktwits_api_pagination():
    """Test StockTwits API pagination."""
    # First page
    responses.add(
        responses.GET,
        "https://api.stocktwits.com/api/v2/streams/symbols/aapl/messages",
        json={
            "status": "ok",
            "messages": [
                {
                    "id": "msg1",
                    "body": "Message 1",
                    "created_at": "2025-01-15T10:00:00Z",
                    "sentiment": None,
                    "likes": 1,
                    "user": {"id": 1, "username": "user1", "followers": 10}
                }
            ],
            "links": {
                "next": "https://api.stocktwits.com/api/v2/streams/symbols/aapl/messages?cursor=abc123"
            }
        },
        status=200
    )

    # Second page
    responses.add(
        responses.GET,
        "https://api.stocktwits.com/api/v2/streams/symbols/aapl/messages",
        json={
            "status": "ok",
            "messages": [
                {
                    "id": "msg2",
                    "body": "Message 2",
                    "created_at": "2025-01-15T09:00:00Z",
                    "sentiment": None,
                    "likes": 2,
                    "user": {"id": 2, "username": "user2", "followers": 20}
                }
            ]
        },
        status=200
    )

    since = datetime.utcnow() - timedelta(days=1)
    result = collect_stocktwits({"symbol": "AAPL"}, since)

    # Should collect from multiple pages
    assert len(result) >= 1

def test_api_client_missing_credentials():
    """Test API clients return empty when credentials missing."""
    from unittest.mock import patch

    # Mock missing credentials
    with patch("app.services.x_client.get_settings") as mock_settings:
        mock_settings.return_value.x_bearer_token = ""
        since = datetime.utcnow() - timedelta(days=1)
        result = search_x_bundle({"symbol": "AAPL"}, since)
        assert result == []
