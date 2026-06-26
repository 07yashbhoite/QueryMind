# QueryMind ML — Presentation Pack

Use this for your demo (5–7 min) and slides (10–15 min total).

---

## Before You Present (checklist)

- [ ] Copy `.env.example` → `.env` and add your Groq API key (rotate the old one if it was in git)
- [ ] Run `pip install -r requirements.txt`
- [ ] Start app: `.\start.ps1` or `python app.py`
- [ ] Open http://localhost:5000 — login as **admin** / **admin123**
- [ ] Run the “warm-up queries” below once (so ML stats & suggester have data)
- [ ] Keep a CSV file ready (e.g. sales with date, product, revenue columns)
- [ ] Optional: record a 2-minute screen capture as backup

---

## Warm-up (run once, don’t show)

Run these on the **Demo DB** so analytics and ML look populated:

1. How many students are there?
2. Show all students from Mumbai
3. What is the average salary of employees?
4. Which course has the most enrollments?
5. List all products with price greater than 10000

---

## Live Demo Script (~6 minutes)

### Part 1 — Problem & core flow (2 min)

**Say:** “Non-technical users need data but can’t write SQL. QueryMind lets them ask in English.”

| Step | Action | What to point out |
|------|--------|-------------------|
| 1 | Login as admin | Session + RBAC |
| 2 | Confirm **Demo DB** connected | 7 tables in sidebar schema |
| 3 | Ask: **"How many students are there?"** | Generated SQL, result table, plain-English explanation |
| 4 | Ask: **"Show all students from Mumbai"** | ML panel: intent = FILTER, confidence % |

**Say:** “Before calling the LLM, a local classifier detects intent and adds a hint — that improves SQL quality.”

---

### Part 2 — Harder query + self-heal (1.5 min)

| Step | Action | What to point out |
|------|--------|-------------------|
| 5 | Ask: **"Which course has the most enrollments?"** | JOIN + aggregate; may show intent JOIN |
| 6 | Ask: **"Show top 3 highest paid employees"** | ORDER BY + LIMIT; intent SORT |

**If SQL fails once:** Point to **“fixed on retry”** badge — self-healing loop.

**Say:** “If execution fails, we send the error back to the model and retry automatically.”

---

### Part 3 — CSV upload (1.5 min)

| Step | Action | What to point out |
|------|--------|-------------------|
| 7 | **Connect** tab → Upload CSV | Preview: delimiter, types, row count |
| 8 | Load file | Converted to SQLite in `uploads/` |
| 9 | Ask: **"What is the total revenue?"** (adjust column names to your CSV) | Same NL pipeline on user data |

**Say:** “Users can upload spreadsheets without setting up a database server.”

---

### Part 4 — Security & admin (1 min)

| Step | Action | What to point out |
|------|--------|-------------------|
| 10 | Open **Settings → Permissions** (or register a second user) | Regular user lacks DELETE |
| 11 | Ask something that maps to DELETE, or show blocked SQL on generate | Permission denied message |
| 12 | Open **Admin** panel | Users, pending requests, activity logs |

**Say:** “Destructive SQL is gated by role. Users can request extra permissions; admin approves.”

---

### Part 5 — ML & analytics (30 sec)

| Step | Action | What to point out |
|------|--------|-------------------|
| 13 | Sidebar stats | Success rate, avg response time |
| 14 | ML stats (if visible) | Intent classes, success predictor, suggestions |

**Say:** “Three local ML modules: intent classifier, success predictor, query suggester — they learn from usage history.”

---

## Sample questions (Demo DB)

| Question | Expected behavior |
|----------|-------------------|
| How many students are there? | COUNT |
| Show all students from Mumbai | WHERE filter |
| What is the average salary of employees? | AVG |
| How many employees are in each department? | GROUP BY |
| Which course has the most enrollments? | JOIN + COUNT/GROUP |
| Show top 3 highest paid employees | ORDER BY + LIMIT |
| List all products with price greater than 10000 | WHERE on numeric |
| Show all delivered orders | Filter on status |
| What is the total budget across all departments? | SUM |
| Find employees earning more than 60000 | WHERE salary |

---

## Slide Outline (8–10 slides)

### Slide 1 — Title
- **QueryMind ML: Natural Language to SQL with Hybrid AI**
- Your name, department, guide name, date

### Slide 2 — Problem Statement
- SQL is powerful but hard for non-technical users
- Businesses store data in SQLite, MySQL, PostgreSQL, CSV/Excel
- **Goal:** Ask questions in English, get accurate answers safely

### Slide 3 — Proposed Solution
- Web app: connect DB → ask question → SQL → results → explanation
- **Hybrid:** Groq LLM (generation) + scikit-learn (intent, success, suggestions)
- RBAC for safe multi-user access

### Slide 4 — System Architecture
Use this diagram on the slide:

```
User → Flask App → [Intent ML] → Groq LLM → SQL
                      ↓              ↓
              Success Predictor   Execute on DB
                      ↓              ↓
              Query Suggester    Explain results
```

Components: Flask, Groq (Llama 3.1), scikit-learn, SQLite/MySQL/PostgreSQL

### Slide 5 — ML Modules (your differentiator)
| Module | Algorithm | Purpose |
|--------|-----------|---------|
| Intent Classifier | TF-IDF + Naive Bayes | Hint for LLM (6 intent types) |
| Success Predictor | Random Forest / GBM | Predict if query will succeed |
| Query Suggester | TF-IDF + cosine similarity | Similar past questions |

- Intent model: ~120 labeled examples, trained locally, saved as `.pkl`

### Slide 6 — Key Features
- Multi-DB + CSV/Excel ingestion
- Self-healing SQL (error → fix → retry)
- RBAC + permission requests + audit log
- Per-user history & analytics

### Slide 7 — Implementation
- **Backend:** Python, Flask
- **Frontend:** HTML/CSS/JS
- **AI:** Groq API (Llama 3.1 8B)
- **ML:** scikit-learn, joblib
- **Storage:** SQLite (demo, history, users)

### Slide 8 — Demo
- Screenshot or live demo (use script above)
- Show: question → SQL → table → explanation → ML badges

### Slide 9 — Results / Evaluation
Fill in your numbers from the app sidebar after warm-up:

- Total queries run: ___
- Success rate: ___%
- Avg response time: ___ ms
- Self-corrected queries: ___
- Intent classifier training accuracy: ~90%+ (from console on first run)

### Slide 10 — Limitations & Future Work
**Limitations:** English only; depends on Groq API; complex schemas may fail; LLM can hallucinate columns

**Future:** On-prem LLM, query caching, charts/export, Spider benchmark, multi-language

### Slide 11 — Conclusion
- QueryMind lowers the barrier to database access
- Hybrid ML + LLM is more reliable than LLM alone
- Production-minded: auth, permissions, logging

### Slide 12 — Q&A
- Thank you / questions

---

## Viva — Quick Answers

**Why ML + LLM?**  
ML runs locally, adds intent hints and learns from your history; LLM handles flexible SQL generation.

**Is it secure?**  
RBAC blocks destructive SQL; passwords hashed (SHA-256); activity logged. API keys belong in `.env`, not source code.

**What if Groq is down?**  
SQL generation fails; intent/suggest still work locally. Mention backup recording for demo.

**Novelty?**  
Not just Text-to-SQL — hybrid pipeline, self-heal, CSV pipeline, RBAC, adaptive ML from usage.

---

## Emergency backup

If live demo fails:
1. Show screenshots from a prior successful run
2. Walk through architecture slide + code in `ml/intent_classifier.py`
3. Show demo DB schema in DB browser or sidebar
