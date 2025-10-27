#!/usr/bin/env python3
"""
Sentiment Bot CLI Tool

Test sentiment analysis without running the full web server.
"""

import argparse
import sys
from datetime import datetime
from typing import Optional
from app.nlp.sentiment import score_text
from app.nlp.clean import normalize_post, extract_symbols
from app.services.resolver import resolve
from app.logging_config import setup_logging, get_logger

setup_logging("INFO")
logger = get_logger(__name__)

def analyze_text(text: str, symbol: Optional[str] = None) -> None:
    """Analyze a single piece of text."""
    print(f"\n{'='*60}")
    print("SENTIMENT ANALYSIS")
    print(f"{'='*60}")
    print(f"Original text: {text}")
    print()

    # Clean text
    cleaned = normalize_post(text)
    print(f"Cleaned text: {cleaned}")
    print()

    # Resolve symbol if provided
    if symbol:
        try:
            resolved = resolve(symbol)
            print(f"Resolved instrument:")
            print(f"  Symbol: {resolved.symbol}")
            print(f"  Company: {resolved.company_name}")
            print()

            # Extract symbols
            inst_dict = resolved.model_dump()
            symbols = extract_symbols(text, inst_dict)
            print(f"Extracted symbols: {symbols}")
            print()
        except Exception as e:
            # Skip resolver if database not available
            logger.debug(f"Symbol resolution skipped (DB not available): {e}")
            print(f"Symbol: {symbol.upper()} (resolution skipped - DB not available)")
            print()

    # Score sentiment
    sentiment = score_text(cleaned)
    print("Sentiment Score:")
    print(f"  Polarity:     {sentiment.polarity:+.3f} ({'positive' if sentiment.polarity > 0 else 'negative' if sentiment.polarity < 0 else 'neutral'})")
    print(f"  Subjectivity: {sentiment.subjectivity:.3f} ({'subjective' if sentiment.subjectivity > 0.5 else 'objective'})")
    print(f"  Sarcasm:      {sentiment.sarcasm_prob:.3f} ({'likely' if sentiment.sarcasm_prob > 0.5 else 'unlikely'})")
    print(f"  Confidence:   {sentiment.confidence:.3f}")
    print(f"  Model:        {sentiment.model}")
    print(f"{'='*60}\n")

def batch_analyze(file_path: str, symbol: Optional[str] = None) -> None:
    """Analyze multiple texts from a file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = [line.strip() for line in f if line.strip()]

        print(f"\nAnalyzing {len(lines)} texts from {file_path}")
        print(f"{'='*60}\n")

        polarities = []
        for i, text in enumerate(lines, 1):
            print(f"Text {i}/{len(lines)}: {text[:50]}...")
            cleaned = normalize_post(text)
            sentiment = score_text(cleaned)
            polarities.append(sentiment.polarity)
            print(f"  → Polarity: {sentiment.polarity:+.3f}, "
                  f"Subjectivity: {sentiment.subjectivity:.3f}, "
                  f"Confidence: {sentiment.confidence:.3f}")
            print()

        # Summary statistics
        avg_polarity = sum(polarities) / len(polarities)
        positive_count = sum(1 for p in polarities if p > 0.1)
        negative_count = sum(1 for p in polarities if p < -0.1)
        neutral_count = len(polarities) - positive_count - negative_count

        print(f"{'='*60}")
        print("SUMMARY")
        print(f"{'='*60}")
        print(f"Total texts:     {len(polarities)}")
        print(f"Positive:        {positive_count} ({positive_count/len(polarities)*100:.1f}%)")
        print(f"Negative:        {negative_count} ({negative_count/len(polarities)*100:.1f}%)")
        print(f"Neutral:         {neutral_count} ({neutral_count/len(polarities)*100:.1f}%)")
        print(f"Average polarity: {avg_polarity:+.3f}")
        print(f"{'='*60}\n")

    except FileNotFoundError:
        logger.error(f"File not found: {file_path}")
        sys.exit(1)
    except Exception as e:
        logger.exception(f"Error reading file: {e}")
        sys.exit(1)

def test_examples() -> None:
    """Run tests with example sentences."""
    examples = [
        ("$AAPL to the moon! 🚀🚀🚀 Best stock ever!", "AAPL"),
        ("$TSLA is crashing hard. Time to sell and cut losses.", "TSLA"),
        ("I think $MSFT will have moderate growth next quarter", "MSFT"),
        ("Yeah right, $GME is definitely going up... 🙄", "GME"),
        ("$AMZN earnings beat expectations! Strong buy!", "AMZN"),
        ("Totally not worried about $NVDA's drop today 😏", "NVDA"),
        ("$META showing solid fundamentals and good technical setup", "META"),
        ("BANKRUPTCY INCOMING!!! $RIVN IS DONE!!!", "RIVN"),
    ]

    print("\n" + "="*60)
    print("RUNNING TEST EXAMPLES")
    print("="*60 + "\n")

    for i, (text, symbol) in enumerate(examples, 1):
        print(f"Example {i}/{len(examples)}")
        analyze_text(text, symbol)

def main():
    parser = argparse.ArgumentParser(
        description="Sentiment Bot CLI - Test sentiment analysis locally",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Analyze single text
  python cli.py --text "AAPL to the moon! 🚀" --symbol AAPL

  # Analyze texts from file
  python cli.py --file posts.txt --symbol TSLA

  # Run test examples
  python cli.py --test

  # Adjust logging level
  python cli.py --test --log-level DEBUG
        """
    )

    parser.add_argument(
        '--text', '-t',
        help='Single text to analyze'
    )
    parser.add_argument(
        '--symbol', '-s',
        help='Stock symbol for context'
    )
    parser.add_argument(
        '--file', '-f',
        help='File containing texts to analyze (one per line)'
    )
    parser.add_argument(
        '--test',
        action='store_true',
        help='Run test examples'
    )
    parser.add_argument(
        '--log-level',
        default='INFO',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        help='Logging level (default: INFO)'
    )

    args = parser.parse_args()

    # Set logging level
    setup_logging(args.log_level)

    # Execute command
    if args.test:
        test_examples()
    elif args.text:
        analyze_text(args.text, args.symbol)
    elif args.file:
        batch_analyze(args.file, args.symbol)
    else:
        parser.print_help()
        sys.exit(1)

if __name__ == '__main__':
    main()
