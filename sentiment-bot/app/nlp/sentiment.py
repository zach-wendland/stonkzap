import logging
from typing import Optional
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch
from app.services.types import SentimentScore

logger = logging.getLogger(__name__)

# Global model cache
_model_cache = {}

def _get_finbert_model():
    """Load FinBERT model (cached after first load)."""
    if "finbert" not in _model_cache:
        try:
            model_name = "ProsusAI/finbert"
            tokenizer = AutoTokenizer.from_pretrained(model_name)
            model = AutoModelForSequenceClassification.from_pretrained(model_name)

            # Use CPU by default (works faster for inference on typical systems)
            device = "cpu"
            model.to(device)
            model.eval()

            _model_cache["finbert"] = (tokenizer, model, device)
            logger.info(f"Loaded FinBERT model on {device}")
        except Exception as e:
            logger.error(f"Failed to load FinBERT: {e}. Falling back to heuristics.")
            return None

    return _model_cache.get("finbert")

def score_text(text: str) -> SentimentScore:
    """
    Score financial sentiment using FinBERT model.

    Falls back to heuristics if model loading fails.

    Args:
        text: Text to analyze for sentiment

    Returns:
        SentimentScore with polarity (-1 to +1) and confidence
    """
    # Try FinBERT first
    model_tuple = _get_finbert_model()

    if model_tuple:
        try:
            tokenizer, model, device = model_tuple

            # Truncate text to max length (512 tokens for BERT)
            max_length = 512
            inputs = tokenizer(
                text[:512],  # Approximate truncation before tokenizing
                return_tensors="pt",
                truncation=True,
                max_length=max_length,
                padding=True
            ).to(device)

            with torch.no_grad():
                outputs = model(**inputs)
                logits = outputs.logits

            # FinBERT has 3 classes: [negative, neutral, positive]
            probabilities = torch.softmax(logits, dim=-1)[0].cpu().numpy()

            # Map classes to sentiment
            # negative = -1, neutral = 0, positive = +1
            polarity = (probabilities[2] - probabilities[0]).item()  # pos - neg

            # Confidence is the highest probability
            confidence = float(probabilities.max())

            # Subjectivity: how confident the model is (opposite of neutral probability)
            subjectivity = 1.0 - float(probabilities[1])

            return SentimentScore(
                polarity=max(-1.0, min(1.0, polarity)),
                subjectivity=subjectivity,
                sarcasm_prob=_detect_sarcasm(text),
                confidence=confidence,
                model="finbert"
            )
        except Exception as e:
            logger.warning(f"FinBERT inference failed: {e}. Falling back to heuristics.")

    # Fallback to heuristics
    return _score_text_heuristic(text)

def _score_text_heuristic(text: str) -> SentimentScore:
    """
    Simple heuristic-based sentiment scoring (fallback).
    """
    positive_words = ['bullish', 'moon', 'buy', 'long', 'growth', 'profit',
                     'gain', 'up', 'surge', 'boom', 'excellent', 'great', 'strong']
    negative_words = ['bearish', 'crash', 'sell', 'short', 'loss', 'down',
                     'dump', 'fall', 'decline', 'terrible', 'bad', 'weak']

    text_lower = text.lower()
    pos_count = sum(1 for word in positive_words if word in text_lower)
    neg_count = sum(1 for word in negative_words if word in text_lower)

    total = pos_count + neg_count
    if total == 0:
        polarity = 0.0
        confidence = 0.3
    else:
        polarity = (pos_count - neg_count) / total
        confidence = min(0.7, total / 5)

    # Subjectivity based on length
    subjectivity = min(1.0, (len(text) / 280) * 0.7)

    return SentimentScore(
        polarity=max(-1.0, min(1.0, polarity)),
        subjectivity=subjectivity,
        sarcasm_prob=_detect_sarcasm(text),
        confidence=confidence,
        model="heuristic"
    )

def _detect_sarcasm(text: str) -> float:
    """
    Detect potential sarcasm in text.

    Returns probability between 0.0 and 1.0
    """
    sarcasm_indicators = {
        'yeah right': 0.8,
        'sure': 0.5,
        '🙄': 0.9,
        'lol': 0.3,
        'obviously': 0.6,
        'brilliant': 0.5,  # Context-dependent
    }

    text_lower = text.lower()
    max_sarcasm = 0.0

    for indicator, score in sarcasm_indicators.items():
        if indicator in text_lower:
            max_sarcasm = max(max_sarcasm, score)

    # Default low probability if no indicators
    return max_sarcasm if max_sarcasm > 0 else 0.05
