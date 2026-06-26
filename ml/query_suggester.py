"""
ML Module 3: Smart Query Suggester
-------------------------------------
Uses TF-IDF vectorization + cosine similarity to find the most
similar successful past queries from a user's history.

When you type a question, this module suggests up to 3 similar
questions that previously produced successful results — helping
you refine your question or reuse working patterns.

Also provides query clustering to group related queries together.
"""

import os
import sqlite3
import numpy as np
import pickle

SUGGESTER_PATH = os.path.join("models", "query_suggester.pkl")


class QuerySuggester:
    def __init__(self):
        self.vectorizer     = None
        self.question_matrix = None
        self.questions      = []
        self.sql_map        = {}
        self._fitted        = False

    def _load_successful_queries(self, user_id=None) -> list:
        """Load successful queries from history."""
        if not os.path.exists("history.db"):
            return []

        conn = sqlite3.connect("history.db")
        cur  = conn.cursor()

        if user_id:
            cur.execute("""
                SELECT DISTINCT question, sql FROM history
                WHERE success=1 AND user_id=? AND length(question) > 5
                ORDER BY id DESC LIMIT 500
            """, (user_id,))
        else:
            cur.execute("""
                SELECT DISTINCT question, sql FROM history
                WHERE success=1 AND length(question) > 5
                ORDER BY id DESC LIMIT 500
            """)

        rows = cur.fetchall()
        conn.close()
        return rows

    def fit(self, user_id=None):
        """Fit TF-IDF vectorizer on successful query history."""
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
        except ImportError:
            return False

        rows = self._load_successful_queries(user_id)
        if len(rows) < 3:
            return False

        self.questions = [r[0] for r in rows]
        self.sql_map   = {r[0]: r[1] for r in rows}

        self.vectorizer = TfidfVectorizer(
            ngram_range=(1, 2),
            max_features=2000,
            sublinear_tf=True,
            stop_words="english"
        )
        self.question_matrix = self.vectorizer.fit_transform(self.questions)
        self._fitted = True

        os.makedirs("models", exist_ok=True)
        with open(SUGGESTER_PATH, "wb") as f:
            pickle.dump({
                "vectorizer":      self.vectorizer,
                "question_matrix": self.question_matrix,
                "questions":       self.questions,
                "sql_map":         self.sql_map,
            }, f)
        return True

    def load(self) -> bool:
        if os.path.exists(SUGGESTER_PATH):
            with open(SUGGESTER_PATH, "rb") as f:
                data = pickle.load(f)
            self.vectorizer      = data["vectorizer"]
            self.question_matrix = data["question_matrix"]
            self.questions       = data["questions"]
            self.sql_map         = data["sql_map"]
            self._fitted         = True
            return True
        return False

    def suggest(self, question: str, top_k: int = 3) -> list:
        """
        Return top-k most similar successful past queries.
        Each result: {question, sql, similarity_pct}
        """
        if not self._fitted:
            if not self.load():
                return []

        try:
            from sklearn.metrics.pairwise import cosine_similarity
        except ImportError:
            return []

        if not self.questions:
            return []

        q_vec = self.vectorizer.transform([question.lower()])
        sims  = cosine_similarity(q_vec, self.question_matrix).flatten()

        top_idx = np.argsort(sims)[::-1][:top_k + 5]  # grab extras, filter below

        suggestions = []
        for idx in top_idx:
            sim = float(sims[idx])
            if sim < 0.10:           # too dissimilar — skip
                continue
            q = self.questions[idx]
            if q.lower().strip() == question.lower().strip():  # exact match — skip
                continue
            suggestions.append({
                "question":   q,
                "sql":        self.sql_map.get(q, ""),
                "similarity": round(sim * 100, 1),
            })
            if len(suggestions) >= top_k:
                break

        return suggestions

    def cluster_queries(self, user_id=None, n_clusters: int = 5) -> list:
        """
        K-Means cluster all user queries into topic groups.
        Returns list of {cluster_id, label, questions[]}
        """
        try:
            from sklearn.cluster import KMeans
            from sklearn.feature_extraction.text import TfidfVectorizer
        except ImportError:
            return []

        rows = self._load_successful_queries(user_id)
        if len(rows) < n_clusters * 2:
            return []

        questions = [r[0] for r in rows]
        n_clusters = min(n_clusters, len(questions) // 2)

        vec = TfidfVectorizer(ngram_range=(1, 2), max_features=1000, stop_words="english")
        X   = vec.fit_transform(questions)

        km = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
        labels = km.fit_predict(X)

        # Get top terms per cluster as label
        order_centroids = km.cluster_centers_.argsort()[:, ::-1]
        terms = vec.get_feature_names_out()

        clusters = []
        for i in range(n_clusters):
            top_terms = [terms[idx] for idx in order_centroids[i, :3]]
            cluster_qs = [questions[j] for j, l in enumerate(labels) if l == i]
            clusters.append({
                "cluster_id": i,
                "label":      " / ".join(top_terms),
                "count":      len(cluster_qs),
                "questions":  cluster_qs[:5],  # sample
            })

        clusters.sort(key=lambda x: x["count"], reverse=True)
        return clusters

    def is_ready(self) -> bool:
        return self._fitted or os.path.exists(SUGGESTER_PATH)


_suggester = QuerySuggester()


def get_suggester() -> QuerySuggester:
    return _suggester


if __name__ == "__main__":
    s = QuerySuggester()
    result = s.fit()
    if result:
        print("Suggester fitted!")
        sug = s.suggest("how many students are there")
        for r in sug:
            print(f"  [{r['similarity']:.0f}%] {r['question']}")
    else:
        print("Not enough history yet. Run some queries first!")
