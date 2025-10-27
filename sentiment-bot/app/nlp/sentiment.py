from app.services.types import SentimentScore

def score_text(text: str) -> SentimentScore:
    # Placeholder using simple heuristics
    # TODO: Replace with FinBERT or financial RoBERTa

    positive_words = ['bullish', 'moon', 'buy', 'long', 'growth', 'profit', 'gain', 'up']
    negative_words = ['bearish', 'crash', 'sell', 'short', 'loss', 'down', 'dump']

    text_lower = text.lower()
    pos_count = sum(1 for word in positive_words if word in text_lower)
    neg_count = sum(1 for word in negative_words if word in text_lower)

    total = pos_count + neg_count
    if total == 0:
        polarity = 0.0
    else:
        polarity = (pos_count - neg_count) / total

    # Simple subjectivity based on length and punctuation
    subjectivity = min(1.0, (len(text) / 280) * 0.7)

    # Sarcasm detection placeholder
    sarcasm_indicators = ['yeah right', 'sure', '🙄']
    sarcasm_prob = 0.8 if any(ind in text_lower for ind in sarcasm_indicators) else 0.1

    confidence = 0.6 if total > 0 else 0.3

    return SentimentScore(
        polarity=max(-1.0, min(1.0, polarity)),
        subjectivity=subjectivity,
        sarcasm_prob=sarcasm_prob,
        confidence=confidence,
        model="simple_heuristic"
    )
