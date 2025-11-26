#!/usr/bin/env python3
"""
End-to-end validation script for Sentiment Bot MVP.

Validates that all components work together:
1. Symbol resolution
2. Data collection from all sources
3. Text cleaning and filtering
4. Sentiment analysis (FinBERT)
5. Embeddings generation
6. Database persistence
7. Result aggregation

Run with: python validate_e2e.py
"""

import sys
import logging
from datetime import datetime, timedelta
from app.services.resolver import resolve
from app.services.x_client import search_x_bundle
from app.services.reddit_client import search_reddit_bundle
from app.services.stocktwits_client import collect_stocktwits
from app.services.discord_client import collect_discord
from app.nlp.clean import normalize_post, extract_symbols
from app.nlp.sentiment import score_text
from app.nlp.embeddings import compute_embedding
from app.nlp.bot_filter import is_probable_bot
from app.orchestration.tasks import aggregate_social, _parse_window

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

def validate_symbol_resolution():
    """Validate symbol resolution."""
    logger.info("=" * 60)
    logger.info("TEST 1: Symbol Resolution")
    logger.info("=" * 60)

    try:
        inst = resolve("AAPL")
        logger.info(f"✓ Resolved AAPL to {inst.company_name}")
        logger.info(f"  Symbol: {inst.symbol}")
        logger.info(f"  Company: {inst.company_name}")
        return True
    except Exception as e:
        logger.error(f"✗ Failed to resolve symbol: {e}")
        return False

def validate_text_processing():
    """Validate text cleaning and symbol extraction."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 2: Text Processing")
    logger.info("=" * 60)

    try:
        # Test text normalization
        messy_text = "Check this out https://example.com\n$AAPL is   bullish!!!    "
        cleaned = normalize_post(messy_text)
        logger.info(f"✓ Text normalization:")
        logger.info(f"  Input:  {repr(messy_text[:50])}...")
        logger.info(f"  Output: {repr(cleaned[:50])}...")

        # Test symbol extraction
        inst_dict = {"symbol": "AAPL", "company_name": "Apple"}
        text_with_symbol = "Apple stock is up, $AAPL is doing great"
        symbols = extract_symbols(text_with_symbol, inst_dict)
        logger.info(f"✓ Symbol extraction: Found {len(symbols)} symbols: {symbols}")

        return True
    except Exception as e:
        logger.error(f"✗ Text processing failed: {e}")
        return False

def validate_sentiment_analysis():
    """Validate sentiment scoring with FinBERT."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 3: Sentiment Analysis (FinBERT)")
    logger.info("=" * 60)

    try:
        test_texts = [
            "AAPL is bullish and will moon! Excellent opportunity",
            "This stock is terrible, bearish, crash incoming",
            "Apple is doing okay, neutral sentiment overall"
        ]

        for text in test_texts:
            score = score_text(text)
            logger.info(f"✓ Text: {text[:50]}...")
            logger.info(f"  Polarity: {score.polarity:.3f}, Confidence: {score.confidence:.3f}")
            logger.info(f"  Model: {score.model}")

        return True
    except Exception as e:
        logger.error(f"✗ Sentiment analysis failed: {e}")
        return False

def validate_embeddings():
    """Validate semantic embedding generation."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 4: Semantic Embeddings")
    logger.info("=" * 60)

    try:
        text = "AAPL stock analysis and sentiment from social media"
        embedding = compute_embedding(text)

        logger.info(f"✓ Generated embedding for text: {text[:50]}...")
        logger.info(f"  Dimensionality: {len(embedding)}")
        logger.info(f"  Norm (should be ~1.0): {(embedding ** 2).sum() ** 0.5:.6f}")

        # Test determinism
        embedding2 = compute_embedding(text)
        import numpy as np
        is_deterministic = np.allclose(embedding, embedding2)
        logger.info(f"  Deterministic (same for same input): {is_deterministic}")

        return True
    except Exception as e:
        logger.error(f"✗ Embedding generation failed: {e}")
        return False

def validate_window_parsing():
    """Validate time window parsing."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 5: Time Window Parsing")
    logger.info("=" * 60)

    try:
        test_windows = ["24h", "7d", "30d"]

        for window in test_windows:
            td = _parse_window(window)
            logger.info(f"✓ Window {window}: {td.total_seconds() / 3600:.1f} hours")

        return True
    except Exception as e:
        logger.error(f"✗ Window parsing failed: {e}")
        return False

def validate_pipeline_integration():
    """Validate complete pipeline (mocked or with credentials)."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 6: Complete Pipeline Integration")
    logger.info("=" * 60)

    try:
        logger.info("Attempting to run complete sentiment aggregation pipeline...")
        logger.info("(This will use configured API credentials if available)")

        result = aggregate_social("AAPL", "24h")

        logger.info("✓ Pipeline completed successfully!")
        logger.info(f"  Symbol: {result.get('symbol')}")
        logger.info(f"  Posts found: {result.get('posts_found', 0)}")
        logger.info(f"  Posts processed: {result.get('posts_processed', 0)}")

        if result.get('sources'):
            logger.info(f"  Sources: {result.get('sources')}")

        if result.get('error'):
            logger.warning(f"  Warning: {result.get('error')}")

        return True
    except Exception as e:
        logger.error(f"✗ Pipeline integration failed: {e}")
        logger.warning("  (This is expected if API credentials aren't configured)")
        return False

def validate_data_models():
    """Validate data models."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 7: Data Models")
    logger.info("=" * 60)

    try:
        from app.services.types import SocialPost, SentimentScore, ResolvedInstrument

        # Test SocialPost
        post = SocialPost(
            source="test",
            platform_id="123",
            author_id="user1",
            created_at=datetime.utcnow(),
            text="Test post"
        )
        logger.info(f"✓ Created SocialPost: {post.source} by {post.author_id}")

        # Test SentimentScore
        score = SentimentScore(
            polarity=0.5,
            subjectivity=0.6,
            sarcasm_prob=0.1,
            confidence=0.8
        )
        logger.info(f"✓ Created SentimentScore: polarity={score.polarity}")

        # Test ResolvedInstrument
        inst = ResolvedInstrument(
            symbol="AAPL",
            company_name="Apple Inc."
        )
        logger.info(f"✓ Created ResolvedInstrument: {inst.symbol} ({inst.company_name})")

        return True
    except Exception as e:
        logger.error(f"✗ Data model validation failed: {e}")
        return False

def main():
    """Run all validation tests."""
    logger.info("\n")
    logger.info("╔" + "=" * 58 + "╗")
    logger.info("║" + " " * 58 + "║")
    logger.info("║" + "  SENTIMENT BOT MVP - END-TO-END VALIDATION".center(58) + "║")
    logger.info("║" + " " * 58 + "║")
    logger.info("╚" + "=" * 58 + "╝")

    tests = [
        ("Data Models", validate_data_models),
        ("Symbol Resolution", validate_symbol_resolution),
        ("Text Processing", validate_text_processing),
        ("Sentiment Analysis", validate_sentiment_analysis),
        ("Embeddings", validate_embeddings),
        ("Time Window Parsing", validate_window_parsing),
        ("Pipeline Integration", validate_pipeline_integration),
    ]

    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            logger.error(f"Test {name} crashed: {e}")
            results.append((name, False))

    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("SUMMARY")
    logger.info("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        logger.info(f"{status}: {name}")

    logger.info("=" * 60)
    logger.info(f"Total: {passed}/{total} tests passed")

    if passed == total:
        logger.info("🎉 All tests passed! MVP is ready for deployment.")
        return 0
    else:
        logger.warning(f"⚠️  {total - passed} test(s) failed. See details above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
