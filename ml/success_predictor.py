"""
ML Module 2: Query Success Predictor
--------------------------------------
A Random Forest classifier that trains on your actual query history
to predict whether a new SQL query will execute successfully.

Features used:
  - Question length (chars, words)
  - Intent probabilities (6 features from the intent classifier)
  - Schema complexity (number of tables in active DB)
  - Hour of day (time-based pattern)
  - Has numeric value in question
  - Has comparison operator words
  - Has aggregation words
  - Has JOIN words

This model RETRAINS automatically every 50 new queries so it
keeps improving as you use the app.
"""

import os
import pickle
import sqlite3
import numpy as np
from datetime import datetime

MODEL_PATH   = os.path.join("models", "success_predictor.pkl")
RETRAIN_EVERY = 50   # retrain after every N new queries


class SuccessPredictor:
    def __init__(self):
        self.model        = None
        self.feature_names = []
        self._query_count = 0

    # ── Feature extraction ─────────────────────────────────────────
    def _extract_features(self, question: str, intent_scores: dict,
                          table_count: int = 5, timestamp: str = None) -> list:
        q = question.lower()
        words = q.split()

        # Linguistic features
        char_len   = len(q)
        word_count = len(words)

        has_number  = int(any(w.replace(',', '').replace('.', '').isdigit() for w in words))
        has_compare = int(any(w in q for w in ["greater", "less", "more", "above", "below", "between", "over", "under"]))
        has_agg     = int(any(w in q for w in ["average", "total", "sum", "count", "maximum", "minimum", "highest", "lowest"]))
        has_join    = int(any(w in q for w in ["with", "and their", "along", "enrolled", "belongs"]))
        has_sort    = int(any(w in q for w in ["top", "highest", "lowest", "sort", "order", "rank", "first", "last"]))
        has_limit   = int(any(w.isdigit() for w in words[:6]))  # small number near start = top-N

        # Intent probability features (from classifier)
        intent_feats = [
            intent_scores.get("AGGREGATE", 0) / 100,
            intent_scores.get("COUNT",     0) / 100,
            intent_scores.get("FILTER",    0) / 100,
            intent_scores.get("JOIN",      0) / 100,
            intent_scores.get("LOOKUP",    0) / 100,
            intent_scores.get("SORT",      0) / 100,
        ]

        # Schema complexity
        schema_feat = min(table_count / 10.0, 1.0)

        # Time feature
        if timestamp:
            try:
                hour = datetime.fromisoformat(timestamp).hour
            except Exception:
                hour = 12
        else:
            hour = datetime.now().hour
        hour_sin = np.sin(2 * np.pi * hour / 24)
        hour_cos = np.cos(2 * np.pi * hour / 24)

        features = (
            [char_len / 200.0, word_count / 30.0,
             has_number, has_compare, has_agg, has_join, has_sort, has_limit]
            + intent_feats
            + [schema_feat, hour_sin, hour_cos]
        )

        self.feature_names = [
            "char_len", "word_count", "has_number", "has_compare",
            "has_agg", "has_join", "has_sort", "has_limit",
            "p_aggregate", "p_count", "p_filter", "p_join", "p_lookup", "p_sort",
            "schema_complexity", "hour_sin", "hour_cos"
        ]
        return features

    # ── Load history from DB ───────────────────────────────────────
    def _load_training_data(self, user_id=None):
        if not os.path.exists("history.db"):
            return [], []

        conn = sqlite3.connect("history.db")
        cur  = conn.cursor()

        if user_id:
            cur.execute(
                "SELECT question, success FROM history WHERE user_id=? ORDER BY id",
                (user_id,)
            )
        else:
            cur.execute("SELECT question, success FROM history ORDER BY id")

        rows = cur.fetchall()
        conn.close()
        return rows

    # ── Train ──────────────────────────────────────────────────────
    def train(self, user_id=None):
        """
        Train on historical query data.
        Needs at least 10 rows to build a meaningful model.
        """
        try:
            from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
            from sklearn.model_selection import cross_val_score
            from sklearn.preprocessing import StandardScaler
            from sklearn.pipeline import Pipeline
        except ImportError:
            print("scikit-learn not installed. Run: pip install scikit-learn")
            return None

        # Lazy import to avoid circular
        from ml.intent_classifier import get_classifier
        clf = get_classifier()

        rows = self._load_training_data(user_id)
        if len(rows) < 10:
            print(f"⚠ Not enough history to train predictor ({len(rows)} rows, need 10+)")
            return None

        X, y = [], []
        for question, success in rows:
            try:
                pred   = clf.predict(question)
                feats  = self._extract_features(question, pred["scores"])
                X.append(feats)
                y.append(int(success))
            except Exception:
                continue

        X = np.array(X)
        y = np.array(y)

        # Use Gradient Boosting if enough data, else Random Forest
        if len(y) >= 30:
            base_clf = GradientBoostingClassifier(
                n_estimators=100, max_depth=3, learning_rate=0.1, random_state=42
            )
        else:
            from sklearn.ensemble import RandomForestClassifier
            base_clf = RandomForestClassifier(
                n_estimators=50, max_depth=5, random_state=42, class_weight="balanced"
            )

        self.model = Pipeline([
            ("scaler", StandardScaler()),
            ("clf",    base_clf),
        ])

        if len(y) >= 20:
            cv_scores = cross_val_score(self.model, X, y, cv=3, scoring="accuracy")
            cv_mean   = cv_scores.mean()
        else:
            cv_mean = None

        self.model.fit(X, y)

        os.makedirs("models", exist_ok=True)
        with open(MODEL_PATH, "wb") as f:
            pickle.dump({"model": self.model, "feature_names": self.feature_names}, f)

        acc_str = f"{cv_mean:.2%}" if cv_mean else "N/A (small dataset)"
        print(f"✅ Success Predictor trained on {len(y)} samples — CV accuracy: {acc_str}")

        success_rate = y.mean() * 100
        return {
            "samples":      len(y),
            "cv_accuracy":  round(cv_mean * 100, 1) if cv_mean else None,
            "success_rate": round(success_rate, 1),
        }

    def load(self) -> bool:
        if os.path.exists(MODEL_PATH):
            with open(MODEL_PATH, "rb") as f:
                data = pickle.load(f)
            self.model         = data["model"]
            self.feature_names = data.get("feature_names", [])
            return True
        return False

    def predict(self, question: str, intent_scores: dict,
                table_count: int = 5) -> dict:
        """
        Predict probability of SQL query success.
        Returns {"will_succeed": bool, "confidence": float, "probability": float}
        """
        if self.model is None:
            if not self.load():
                # No model yet — return neutral prediction
                return {"will_succeed": True, "confidence": 50.0, "probability": 0.5, "trained": False}

        feats = self._extract_features(question, intent_scores, table_count)
        X     = np.array([feats])

        proba       = self.model.predict_proba(X)[0]
        # proba[1] = probability of success (class=1)
        success_prob = float(proba[1]) if len(proba) > 1 else float(proba[0])

        return {
            "will_succeed":  success_prob >= 0.5,
            "confidence":    round(max(success_prob, 1 - success_prob) * 100, 1),
            "probability":   round(success_prob * 100, 1),
            "trained":       True,
        }

    def maybe_retrain(self, user_id=None):
        """Retrain if enough new data has accumulated."""
        self._query_count += 1
        if self._query_count >= RETRAIN_EVERY:
            self._query_count = 0
            self.train(user_id)

    def get_feature_importance(self) -> list:
        """Return feature importances (only works with tree-based models)."""
        if self.model is None:
            self.load()
        if self.model is None:
            return []

        try:
            inner = self.model.named_steps["clf"]
            if hasattr(inner, "feature_importances_"):
                imps = inner.feature_importances_
                names = self.feature_names or [f"f{i}" for i in range(len(imps))]
                pairs = sorted(zip(names, imps), key=lambda x: x[1], reverse=True)
                return [{"feature": n, "importance": round(float(v) * 100, 1)} for n, v in pairs]
        except Exception:
            pass
        return []

    def is_trained(self) -> bool:
        return os.path.exists(MODEL_PATH)


_predictor = SuccessPredictor()


def get_predictor() -> SuccessPredictor:
    return _predictor


if __name__ == "__main__":
    p = SuccessPredictor()
    result = p.train()
    if result:
        print(result)
    else:
        print("Not enough history data yet. Run some queries first!")
