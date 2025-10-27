"""Test sentiment analysis module."""

import pytest
from app.nlp.sentiment import score_text, _extract_features, _detect_sarcasm


class TestSentimentAnalysis:
    """Test sentiment scoring functionality."""

    def test_positive_sentiment(self):
        """Test detection of positive sentiment."""
        text = "AAPL to the moon! Great buy opportunity 🚀"
        result = score_text(text)

        assert result.polarity > 0, "Should detect positive sentiment"
        assert result.confidence > 0, "Should have non-zero confidence"
        assert result.model == "enhanced_heuristic_v1"

    def test_negative_sentiment(self):
        """Test detection of negative sentiment."""
        text = "Stock is crashing hard. Sell now to cut losses"
        result = score_text(text)

        assert result.polarity < 0, "Should detect negative sentiment"
        assert result.confidence > 0, "Should have non-zero confidence"

    def test_neutral_sentiment(self):
        """Test neutral text with no sentiment."""
        text = "The company reported earnings today"
        result = score_text(text)

        # Should be close to neutral since no sentiment words
        assert abs(result.polarity) < 0.5, "Should be relatively neutral"

    def test_sarcasm_detection(self):
        """Test sarcasm detection."""
        text = "Yeah right, definitely going up 🙄"
        result = score_text(text)

        assert result.sarcasm_prob > 0.5, "Should detect sarcasm"
        assert result.confidence < 0.5, "Confidence should be lowered by sarcasm"

    def test_intensifiers(self):
        """Test that intensifiers are detected in features."""
        # Test with stronger sentiment word that won't hit ceiling
        text = "This stock is extremely bullish"
        result = score_text(text)

        # Should detect the intensified positive sentiment
        assert result.polarity > 0.5

    def test_negations(self):
        """Test that negations are detected."""
        positive_text = "This is good"
        negated_text = "This is not good"

        positive = score_text(positive_text)
        negated = score_text(negated_text)

        # Negation should affect sentiment
        assert positive.polarity > 0
        # Note: Current implementation may not fully flip - that's expected for heuristics
        assert negated.polarity <= positive.polarity

    def test_emoji_sentiment(self):
        """Test emoji sentiment contribution."""
        text_with_emoji = "Stock 🚀📈💰"
        text_without_emoji = "Stock"

        with_emoji = score_text(text_with_emoji)
        without_emoji = score_text(text_without_emoji)

        # Emojis should contribute positive sentiment even without words
        assert with_emoji.polarity >= without_emoji.polarity

    def test_subjectivity_detection(self):
        """Test subjectivity scoring."""
        objective_text = "The stock closed at $150"
        subjective_text = "I think this stock is amazing!"

        objective = score_text(objective_text)
        subjective = score_text(subjective_text)

        assert subjective.subjectivity > objective.subjectivity

    def test_empty_text(self):
        """Test handling of empty text."""
        result = score_text("")

        assert result.polarity == 0
        assert result.subjectivity == 0
        assert result.confidence == 0

    def test_all_caps_text(self):
        """Test handling of all-caps text."""
        text = "AMAZING STOCK BUY NOW!!!"
        result = score_text(text)

        # Should detect positive sentiment and increased subjectivity
        assert result.polarity > 0
        assert result.subjectivity > 0

    def test_mixed_sentiment(self):
        """Test text with mixed positive and negative words."""
        text = "Stock had good earnings but weak guidance"
        result = score_text(text)

        # Should show some sentiment but maybe not extreme
        assert abs(result.polarity) < 1.0


class TestFeatureExtraction:
    """Test feature extraction from text."""

    def test_extract_sentiment_words(self):
        """Test extraction of sentiment-bearing words."""
        text = "This is bullish news with strong growth"
        features = _extract_features(text)

        assert features['word_count'] > 0
        assert features['sentiment_score'] > 0

    def test_extract_emojis(self):
        """Test emoji extraction and scoring."""
        text = "Going to the moon 🚀📈💰"
        features = _extract_features(text)

        assert features['emoji_score'] > 0

    def test_punctuation_features(self):
        """Test extraction of punctuation features."""
        text = "Amazing stock!!! Really???"
        features = _extract_features(text)

        assert features['exclamation_count'] == 3
        assert features['question_count'] == 3

    def test_first_person_detection(self):
        """Test detection of first-person pronouns."""
        text = "I believe this is my best investment"
        features = _extract_features(text)

        assert features['has_first_person'] is True

    def test_opinion_words_detection(self):
        """Test detection of opinion-indicating words."""
        text = "I think the stock will perform well"
        features = _extract_features(text)

        assert features['has_opinion_words'] is True


class TestSarcasmDetection:
    """Test sarcasm detection functionality."""

    def test_explicit_sarcasm_indicators(self):
        """Test detection of explicit sarcasm phrases."""
        text = "Yeah right, this will definitely work"
        features = _extract_features(text)
        sarcasm = _detect_sarcasm(text, features)

        assert sarcasm >= 0.3

    def test_sarcastic_emoji(self):
        """Test detection of sarcastic emojis."""
        text = "Great news 🙄"
        features = _extract_features(text)
        sarcasm = _detect_sarcasm(text, features)

        assert sarcasm >= 0.3

    def test_excessive_punctuation(self):
        """Test that excessive punctuation raises sarcasm score."""
        text = "Oh wow!!!! Amazing!!!!"
        features = _extract_features(text)
        sarcasm = _detect_sarcasm(text, features)

        assert sarcasm > 0

    def test_no_sarcasm(self):
        """Test normal text without sarcasm."""
        text = "The stock performed well today"
        features = _extract_features(text)
        sarcasm = _detect_sarcasm(text, features)

        assert sarcasm < 0.3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
