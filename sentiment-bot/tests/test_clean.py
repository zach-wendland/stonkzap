"""Test text cleaning and symbol extraction."""

import pytest
from app.nlp.clean import normalize_post, extract_symbols


class TestNormalizePost:
    """Test text normalization functionality."""

    def test_remove_urls(self):
        """Test removal of URLs from text."""
        text = "Check this out https://example.com great stock"
        result = normalize_post(text)

        assert "https://" not in result
        assert "example.com" not in result
        assert "great stock" in result

    def test_remove_multiple_urls(self):
        """Test removal of multiple URLs."""
        text = "News: http://link1.com and https://link2.com"
        result = normalize_post(text)

        assert "http://" not in result
        assert "https://" not in result

    def test_normalize_whitespace(self):
        """Test normalization of excessive whitespace."""
        text = "This  has    too     much     space"
        result = normalize_post(text)

        assert "  " not in result
        assert result == "This has too much space"

    def test_strip_whitespace(self):
        """Test stripping of leading/trailing whitespace."""
        text = "   surrounded by spaces   "
        result = normalize_post(text)

        assert result == "surrounded by spaces"

    def test_empty_text(self):
        """Test handling of empty text."""
        result = normalize_post("")
        assert result == ""

    def test_preserve_content(self):
        """Test that meaningful content is preserved."""
        text = "AAPL earnings beat expectations!"
        result = normalize_post(text)

        assert "AAPL" in result
        assert "earnings" in result
        assert "expectations" in result


class TestExtractSymbols:
    """Test symbol extraction functionality."""

    def test_extract_cashtags(self):
        """Test extraction of cashtag symbols."""
        text = "$AAPL and $TSLA are trending"
        inst = {"symbol": "MSFT", "company_name": "Microsoft"}
        symbols = extract_symbols(text, inst)

        assert "AAPL" in symbols
        assert "TSLA" in symbols

    def test_extract_single_cashtag(self):
        """Test extraction of single cashtag."""
        text = "Buying $NVDA today"
        inst = {"symbol": "NVDA", "company_name": "NVIDIA"}
        symbols = extract_symbols(text, inst)

        assert "NVDA" in symbols
        assert len(symbols) >= 1

    def test_match_instrument_symbol(self):
        """Test that instrument symbol is included when mentioned."""
        text = "AAPL had great earnings"
        inst = {"symbol": "AAPL", "company_name": "Apple"}
        symbols = extract_symbols(text, inst)

        assert "AAPL" in symbols

    def test_match_company_name(self):
        """Test that company name triggers symbol inclusion."""
        text = "Apple released new products"
        inst = {"symbol": "AAPL", "company_name": "Apple"}
        symbols = extract_symbols(text, inst)

        assert "AAPL" in symbols

    def test_case_insensitive_matching(self):
        """Test case-insensitive symbol matching."""
        text = "apple is doing well"
        inst = {"symbol": "AAPL", "company_name": "Apple"}
        symbols = extract_symbols(text, inst)

        assert "AAPL" in symbols

    def test_no_symbols(self):
        """Test text with no extractable symbols."""
        text = "The market looks interesting today"
        inst = {"symbol": "AAPL", "company_name": "Apple"}
        symbols = extract_symbols(text, inst)

        # Should return empty list or only instrument if no matches
        assert isinstance(symbols, list)

    def test_multiple_same_symbol(self):
        """Test that duplicate symbols are deduplicated."""
        text = "$AAPL $AAPL $AAPL"
        inst = {"symbol": "AAPL", "company_name": "Apple"}
        symbols = extract_symbols(text, inst)

        # Should only have one AAPL
        assert symbols.count("AAPL") == 1

    def test_valid_ticker_format(self):
        """Test that only valid ticker formats are extracted."""
        text = "$A $AA $AAA $AAAA $AAAAA $AAAAAA"
        inst = {"symbol": "MSFT", "company_name": "Microsoft"}
        symbols = extract_symbols(text, inst)

        # Should extract 1-5 letter tickers only
        assert "AAAAAA" not in symbols

    def test_no_partial_word_match(self):
        """Test that partial word matches don't extract symbols."""
        text = "ANNOUNCEMENT: earnings call today"
        inst = {"symbol": "AAPL", "company_name": "Apple"}
        symbols = extract_symbols(text, inst)

        # Should not extract random capital letters within words
        assert "ANNOUNCEMENT" not in symbols


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
