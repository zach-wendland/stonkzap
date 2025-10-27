import re
from typing import Dict, List
from app.services.types import SentimentScore
from app.logging_config import get_logger

logger = get_logger(__name__)

# Financial sentiment lexicons
POSITIVE_WORDS = {
    # Strong positive
    'bullish': 2.0, 'moon': 2.0, 'rocket': 2.0, 'surge': 2.0, 'rally': 2.0,
    'breakout': 2.0, 'explosive': 2.0, 'soaring': 2.0,
    # Moderate positive
    'buy': 1.5, 'long': 1.5, 'growth': 1.5, 'profit': 1.5, 'gain': 1.5,
    'up': 1.5, 'strong': 1.5, 'upgrade': 1.5, 'outperform': 1.5,
    # Weak positive
    'good': 1.0, 'positive': 1.0, 'optimistic': 1.0, 'uptrend': 1.0,
    'recover': 1.0, 'beat': 1.0, 'exceed': 1.0
}

NEGATIVE_WORDS = {
    # Strong negative
    'bearish': -2.0, 'crash': -2.0, 'collapse': -2.0, 'plunge': -2.0,
    'dump': -2.0, 'tank': -2.0, 'disaster': -2.0, 'bankruptcy': -2.0,
    # Moderate negative
    'sell': -1.5, 'short': -1.5, 'loss': -1.5, 'down': -1.5, 'weak': -1.5,
    'decline': -1.5, 'fall': -1.5, 'drop': -1.5, 'downgrade': -1.5,
    # Weak negative
    'bad': -1.0, 'negative': -1.0, 'pessimistic': -1.0, 'downtrend': -1.0,
    'miss': -1.0, 'underperform': -1.0, 'concern': -1.0, 'worry': -1.0
}

INTENSIFIERS = ['very', 'extremely', 'really', 'absolutely', 'totally', 'definitely']
DIMINISHERS = ['somewhat', 'slightly', 'kind of', 'sort of', 'maybe', 'perhaps']
NEGATIONS = ['not', 'no', 'never', 'neither', 'nobody', 'nothing', 'nowhere', 'none']

SARCASM_INDICATORS = [
    'yeah right', 'sure thing', 'totally not', 'definitely not',
    '🙄', '😏', '😒', 'obviously', 'clearly'
]

EMOJI_SENTIMENT = {
    '🚀': 2.0, '📈': 1.5, '💎': 1.5, '🙌': 1.5, '💰': 1.5,
    '📉': -1.5, '💀': -2.0, '😭': -1.5, '😱': -1.5, '🔥': 1.0
}

def _extract_features(text: str) -> Dict:
    """Extract linguistic features from text."""
    text_lower = text.lower()

    # Count sentiment words
    sentiment_score = 0.0
    word_count = 0

    # Tokenize and analyze
    words = re.findall(r'\b\w+\b', text_lower)

    for i, word in enumerate(words):
        # Check for sentiment words
        if word in POSITIVE_WORDS:
            score = POSITIVE_WORDS[word]

            # Check for intensifiers or diminishers
            if i > 0:
                prev_word = words[i - 1]
                if prev_word in INTENSIFIERS:
                    score *= 1.5
                elif prev_word in DIMINISHERS:
                    score *= 0.5
                elif prev_word in NEGATIONS:
                    score *= -1

            sentiment_score += score
            word_count += 1

        elif word in NEGATIVE_WORDS:
            score = NEGATIVE_WORDS[word]

            # Check for intensifiers or diminishers
            if i > 0:
                prev_word = words[i - 1]
                if prev_word in INTENSIFIERS:
                    score *= 1.5
                elif prev_word in DIMINISHERS:
                    score *= 0.5
                elif prev_word in NEGATIONS:
                    score *= -1

            sentiment_score += score
            word_count += 1

    # Analyze emojis
    emoji_score = sum(EMOJI_SENTIMENT.get(char, 0) for char in text)

    # Analyze punctuation
    exclamation_count = text.count('!')
    question_count = text.count('?')
    caps_ratio = sum(1 for c in text if c.isupper()) / max(len(text), 1)

    # Calculate subjectivity indicators
    has_first_person = any(word in words for word in ['i', 'my', 'me', 'mine'])
    has_opinion_words = any(word in words for word in ['think', 'believe', 'feel', 'opinion'])

    return {
        'sentiment_score': sentiment_score,
        'word_count': word_count,
        'emoji_score': emoji_score,
        'exclamation_count': exclamation_count,
        'question_count': question_count,
        'caps_ratio': caps_ratio,
        'has_first_person': has_first_person,
        'has_opinion_words': has_opinion_words,
        'total_words': len(words)
    }

def _detect_sarcasm(text: str, features: Dict) -> float:
    """Detect potential sarcasm in text."""
    text_lower = text.lower()
    sarcasm_score = 0.0

    # Check for explicit sarcasm indicators
    for indicator in SARCASM_INDICATORS:
        if indicator in text_lower:
            sarcasm_score += 0.3

    # High caps ratio + positive sentiment might indicate sarcasm
    if features['caps_ratio'] > 0.5 and features['sentiment_score'] > 0:
        sarcasm_score += 0.2

    # Excessive punctuation
    if features['exclamation_count'] > 3:
        sarcasm_score += 0.1

    # Multiple question marks (e.g., "Really???")
    if text.count('??') > 0:
        sarcasm_score += 0.2

    return min(1.0, sarcasm_score)

def score_text(text: str) -> SentimentScore:
    """
    Score sentiment of financial text using enhanced heuristics.

    TODO: Replace with FinBERT or financial RoBERTa for production use.
    """
    if not text or not text.strip():
        logger.warning("Empty text provided for sentiment scoring")
        return SentimentScore(
            polarity=0.0,
            subjectivity=0.0,
            sarcasm_prob=0.0,
            confidence=0.0,
            model="enhanced_heuristic_v1"
        )

    # Extract features
    features = _extract_features(text)

    # Calculate polarity
    if features['word_count'] > 0:
        # Normalize by word count and add emoji influence
        polarity = (features['sentiment_score'] / features['word_count']) + (features['emoji_score'] * 0.3)
        polarity = max(-1.0, min(1.0, polarity))
    else:
        polarity = 0.0

    # Calculate subjectivity (0 = objective, 1 = subjective)
    subjectivity = 0.0
    if features['has_first_person']:
        subjectivity += 0.3
    if features['has_opinion_words']:
        subjectivity += 0.3
    if features['exclamation_count'] > 0:
        subjectivity += min(0.2, features['exclamation_count'] * 0.1)
    if features['caps_ratio'] > 0.3:
        subjectivity += 0.2

    subjectivity = min(1.0, subjectivity)

    # Detect sarcasm
    sarcasm_prob = _detect_sarcasm(text, features)

    # Calculate confidence
    confidence = 0.3  # Base confidence for heuristics
    if features['word_count'] >= 3:
        confidence += 0.2
    if features['word_count'] >= 5:
        confidence += 0.2
    if features['emoji_score'] != 0:
        confidence += 0.1
    # Lower confidence if sarcasm detected
    if sarcasm_prob > 0.5:
        confidence *= 0.5

    confidence = min(1.0, confidence)

    logger.debug(f"Sentiment scored: polarity={polarity:.2f}, subjectivity={subjectivity:.2f}, "
                f"sarcasm={sarcasm_prob:.2f}, confidence={confidence:.2f}")

    return SentimentScore(
        polarity=polarity,
        subjectivity=subjectivity,
        sarcasm_prob=sarcasm_prob,
        confidence=confidence,
        model="enhanced_heuristic_v1"
    )
