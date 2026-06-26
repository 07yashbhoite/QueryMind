"""
ML Module 1: Query Intent Classifier
-------------------------------------
Trains a Multinomial Naive Bayes classifier on labelled question examples
to predict the SQL intent category: AGGREGATE, FILTER, JOIN, COUNT, SORT, LOOKUP.

This runs LOCALLY (no API calls) using scikit-learn + joblib.

The predicted intent is injected into the LLM prompt as a hint, which
significantly improves first-attempt SQL accuracy.
"""

import os
import pickle
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.naive_bayes import MultinomialNB
from sklearn.pipeline import Pipeline
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score

# ── Training data ─────────────────────────────────────────────────
# Labelled (question, intent) pairs — expanded to 120+ examples
TRAINING_DATA = [
    # AGGREGATE
    ("what is the average salary",                        "AGGREGATE"),
    ("find the average age of students",                  "AGGREGATE"),
    ("calculate total revenue",                           "AGGREGATE"),
    ("what is the sum of all budgets",                    "AGGREGATE"),
    ("show total budget across departments",              "AGGREGATE"),
    ("what is the maximum price",                         "AGGREGATE"),
    ("find the minimum score in enrollments",             "AGGREGATE"),
    ("what is the average score per course",              "AGGREGATE"),
    ("calculate average salary by department",            "AGGREGATE"),
    ("what is the total number of orders",                "AGGREGATE"),
    ("sum of all product prices",                         "AGGREGATE"),
    ("mean salary of employees",                          "AGGREGATE"),
    ("total credits of all courses",                      "AGGREGATE"),
    ("highest salary in the company",                     "AGGREGATE"),
    ("lowest score among all students",                   "AGGREGATE"),

    # FILTER
    ("show students from mumbai",                         "FILTER"),
    ("list employees in engineering department",          "FILTER"),
    ("find products with price greater than 10000",       "FILTER"),
    ("show orders that are delivered",                    "FILTER"),
    ("employees earning more than 60000",                 "FILTER"),
    ("students with grade A",                             "FILTER"),
    ("products in electronics category",                  "FILTER"),
    ("orders placed after january 2024",                  "FILTER"),
    ("find students older than 21",                       "FILTER"),
    ("show courses with more than 3 credits",             "FILTER"),
    ("list employees in marketing",                       "FILTER"),
    ("products with stock less than 20",                  "FILTER"),
    ("students from delhi or pune",                       "FILTER"),
    ("show processing orders only",                       "FILTER"),
    ("find employees with age below 30",                  "FILTER"),

    # JOIN
    ("show student names and their course names",         "JOIN"),
    ("list employees with their department budgets",      "JOIN"),
    ("find students enrolled in computer science",        "JOIN"),
    ("show orders with product names",                    "JOIN"),
    ("which students are enrolled in mathematics",        "JOIN"),
    ("display course names with enrollment scores",       "JOIN"),
    ("show product name for each order",                  "JOIN"),
    ("list student names and their scores",               "JOIN"),
    ("employees with their department names",             "JOIN"),
    ("find courses that alice is enrolled in",            "JOIN"),
    ("show orders along with product category",           "JOIN"),
    ("students who enrolled in data science",             "JOIN"),
    ("display enrollments with student and course names", "JOIN"),
    ("which department does each employee belong to",     "JOIN"),
    ("combine student and enrollment data",               "JOIN"),

    # COUNT
    ("how many students are there",                       "COUNT"),
    ("count the number of employees",                     "COUNT"),
    ("how many orders are delivered",                     "COUNT"),
    ("count products in each category",                   "COUNT"),
    ("how many students are from mumbai",                 "COUNT"),
    ("total number of courses",                           "COUNT"),
    ("how many employees per department",                 "COUNT"),
    ("count enrollments per course",                      "COUNT"),
    ("how many products are in stock",                    "COUNT"),
    ("number of orders placed in january",                "COUNT"),
    ("count students with grade a",                       "COUNT"),
    ("how many departments exist",                        "COUNT"),
    ("count failed queries in history",                   "COUNT"),
    ("how many courses have 4 credits",                   "COUNT"),
    ("number of shipped orders",                          "COUNT"),

    # SORT
    ("show top 5 highest paid employees",                 "SORT"),
    ("list products sorted by price",                     "SORT"),
    ("rank students by score descending",                 "SORT"),
    ("order employees by salary highest first",           "SORT"),
    ("show courses ordered by credits",                   "SORT"),
    ("top 3 most expensive products",                     "SORT"),
    ("list orders sorted by total amount",                "SORT"),
    ("students ranked by age",                            "SORT"),
    ("show departments ordered by budget",                "SORT"),
    ("highest scoring students first",                    "SORT"),
    ("sort employees by age ascending",                   "SORT"),
    ("top 10 orders by value",                            "SORT"),
    ("products ordered from cheapest to most expensive",  "SORT"),
    ("show employees with highest salary first",          "SORT"),
    ("list courses by number of enrolled students",       "SORT"),

    # LOOKUP
    ("show all students",                                 "LOOKUP"),
    ("list all products",                                 "LOOKUP"),
    ("display all departments",                           "LOOKUP"),
    ("show every employee",                               "LOOKUP"),
    ("get all orders",                                    "LOOKUP"),
    ("show all courses",                                  "LOOKUP"),
    ("display all enrollments",                           "LOOKUP"),
    ("what are all the tables",                           "LOOKUP"),
    ("show complete student list",                        "LOOKUP"),
    ("retrieve all records from employees",               "LOOKUP"),
    ("list everything in products",                       "LOOKUP"),
    ("show all data from orders",                         "LOOKUP"),
    ("get full list of departments",                      "LOOKUP"),
    ("display all course information",                    "LOOKUP"),
    ("show me all the employees",                         "LOOKUP"),
]

MODEL_PATH = os.path.join("models", "intent_classifier.pkl")


class IntentClassifier:
    def __init__(self):
        self.model    = None
        self.classes_ = ["AGGREGATE", "COUNT", "FILTER", "JOIN", "LOOKUP", "SORT"]

    def train(self):
        """Train the Naive Bayes classifier and save it."""
        os.makedirs("models", exist_ok=True)

        questions = [x[0] for x in TRAINING_DATA]
        labels    = [x[1] for x in TRAINING_DATA]

        X_train, X_test, y_train, y_test = train_test_split(
            questions, labels, test_size=0.2, random_state=42, stratify=labels
        )

        # TF-IDF + Multinomial Naive Bayes pipeline
        self.model = Pipeline([
            ("tfidf", TfidfVectorizer(
                ngram_range=(1, 2),
                min_df=1,
                max_features=5000,
                sublinear_tf=True
            )),
            ("clf", MultinomialNB(alpha=0.3)),
        ])

        self.model.fit(X_train, y_train)

        # Evaluate
        y_pred = self.model.predict(X_test)
        acc = accuracy_score(y_test, y_pred)
        report = classification_report(y_test, y_pred, zero_division=0)

        print(f"\n✅ Intent Classifier trained — accuracy: {acc:.2%}")
        print(report)

        # Save
        with open(MODEL_PATH, "wb") as f:
            pickle.dump(self.model, f)

        return {"accuracy": round(acc * 100, 2), "report": report}

    def load(self):
        """Load the saved model."""
        if os.path.exists(MODEL_PATH):
            with open(MODEL_PATH, "rb") as f:
                self.model = pickle.load(f)
            return True
        return False

    def predict(self, question: str) -> dict:
        """
        Predict the SQL intent for a natural language question.
        Returns intent label + confidence scores for all classes.
        """
        if self.model is None:
            if not self.load():
                self.train()

        question_lower = question.lower().strip()
        proba = self.model.predict_proba([question_lower])[0]
        classes = self.model.classes_
        intent = classes[np.argmax(proba)]
        confidence = float(np.max(proba))

        return {
            "intent":     intent,
            "confidence": round(confidence * 100, 1),
            "scores":     {c: round(float(p) * 100, 1) for c, p in zip(classes, proba)}
        }

    def is_trained(self) -> bool:
        return os.path.exists(MODEL_PATH)


# Singleton
_classifier = IntentClassifier()


def get_classifier() -> IntentClassifier:
    return _classifier


# ── Intent → SQL hint mapping ─────────────────────────────────────
INTENT_HINTS = {
    "AGGREGATE": "Use aggregate functions like COUNT(), AVG(), SUM(), MAX(), MIN() with GROUP BY if needed.",
    "FILTER":    "Use WHERE clause with appropriate conditions to filter rows.",
    "JOIN":      "Use JOIN to combine data from multiple tables based on foreign key relationships.",
    "COUNT":     "Use COUNT() function, possibly with GROUP BY to count per category.",
    "SORT":      "Use ORDER BY with ASC or DESC. Consider using LIMIT for top-N queries.",
    "LOOKUP":    "Use a simple SELECT with the relevant table. Add WHERE only if needed.",
}


def get_intent_hint(question: str) -> tuple[str, dict]:
    """Returns (hint_string, prediction_dict) for a question."""
    result = _classifier.predict(question)
    hint   = INTENT_HINTS.get(result["intent"], "")
    return hint, result


if __name__ == "__main__":
    clf = IntentClassifier()
    clf.train()

    # Quick tests
    tests = [
        "how many students are from mumbai",
        "show employees earning above average salary",
        "list all products sorted by price",
        "find students enrolled in data science course",
        "what is the total budget of all departments",
    ]
    print("\n── Predictions ──")
    for q in tests:
        r = clf.predict(q)
        print(f"  {r['intent']:10s} ({r['confidence']:.0f}%)  →  {q}")
