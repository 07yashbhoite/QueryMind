"""
QueryMind ML Package
=====================
Three ML modules that enhance the Text-to-SQL pipeline:

1. intent_classifier  — NLP classifier (Naive Bayes) for query intent
2. success_predictor  — Random Forest predictor for query success
3. query_suggester    — TF-IDF + cosine similarity for smart suggestions
"""

from ml.intent_classifier import get_classifier, get_intent_hint
from ml.success_predictor import get_predictor
from ml.query_suggester   import get_suggester

__all__ = ["get_classifier", "get_intent_hint", "get_predictor", "get_suggester"]
