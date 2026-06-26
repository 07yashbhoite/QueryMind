"""
Train all ML models in one go.
Run: python -m ml.train_all
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from ml.intent_classifier import IntentClassifier
from ml.success_predictor import SuccessPredictor
from ml.query_suggester   import QuerySuggester

def main():
    print("=" * 50)
    print("  QueryMind — ML Training Pipeline")
    print("=" * 50)

    print("\n[1/3] Training Intent Classifier...")
    clf    = IntentClassifier()
    result = clf.train()
    print(f"      Accuracy: {result['accuracy']}%")

    print("\n[2/3] Training Success Predictor...")
    pred   = SuccessPredictor()
    result = pred.train()
    if result:
        print(f"      Samples: {result['samples']}, CV Accuracy: {result.get('cv_accuracy', 'N/A')}%")
    else:
        print("      Skipped — not enough query history yet (need 10+ queries)")

    print("\n[3/3] Fitting Query Suggester...")
    sug    = QuerySuggester()
    result = sug.fit()
    if result:
        print(f"      Fitted on {len(sug.questions)} successful queries")
    else:
        print("      Skipped — not enough query history yet (need 3+ queries)")

    print("\n✅ Training complete! Models saved to ./models/")
    print("   Restart app.py to use updated models.\n")

if __name__ == "__main__":
    main()
