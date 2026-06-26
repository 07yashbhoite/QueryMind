# QueryMind ML — Text to SQL with Local Database & CSV Support

Connect to any data source and query it in plain English using AI + ML.

## Supported Data Sources

| Source | How to connect |
|--------|----------------|
| SQLite .db | Enter full path: `C:\Users\you\mydb.db` or `/home/you/mydb.db` |
| SQLite upload | Upload a `.db` file via the browser |
| **CSV upload** | **Upload any `.csv` file — auto-converted to a queryable SQLite table** |
| MySQL | `mysql://user:password@localhost:3306/dbname` |
| PostgreSQL | `postgresql://user:password@localhost:5432/dbname` |
| Demo DB | Built-in sample database (7 tables, pre-loaded) |

## CSV Upload Features

- **Auto-detects delimiter** — comma, semicolon, tab, pipe
- **Auto-detects column types** — INTEGER, REAL, TEXT per column
- **Cleans column names** — spaces → underscores, removes special chars
- **Live preview** — see first 3 rows and inferred types before loading
- **Custom table name** — set the SQL table name, or use auto (from filename)
- **No size limit** — large CSVs are streamed efficiently
- **Persists as SQLite** — CSV is converted to a `.db` file in `uploads/`

## Project Structure

```
querymind/
├── app.py                  # Flask app — all routes
├── db_connector.py         # SQLite / MySQL / PostgreSQL connections
├── csv_handler.py          # CSV → SQLite converter (NEW)
├── database.py             # Demo database setup
├── history.py              # Per-user query history
├── schema_linker.py        # SQLite schema extraction (legacy)
├── validator.py            # SQL validation (legacy)
├── requirements.txt
├── ml/
│   ├── intent_classifier.py
│   ├── success_predictor.py
│   ├── query_suggester.py
│   ├── train_all.py
│   └── __init__.py
├── models/                 # Saved ML model .pkl files
├── templates/
│   ├── index.html          # Main app UI
│   └── login.html          # Login / Register
└── uploads/                # Uploaded .db and .csv files
```

## Steps to Run

### 1 — Install dependencies
```bash
pip install -r requirements.txt
```

### 2 — Optional: database drivers
```bash
pip install pymysql           # only for MySQL
pip install psycopg2-binary   # only for PostgreSQL
```

### 3 — Add Groq API key
Copy `.env.example` to `.env` and paste your key:
```bash
copy .env.example .env
```
Free key at: https://console.groq.com

Or set for one PowerShell session:
```powershell
$env:GROQ_API_KEY="your_key_here"
```

### 4 — Run
```powershell
.\start.ps1
```
Or:
```bash
python app.py
```
Open: http://localhost:5000

### 5 — Connect your data source
Register → use the connection panel at the top of the page:

- **📂 Local Path** — full path to any `.db` file on your machine
- **⬆ Upload .db** — drag & drop a SQLite `.db` file
- **📊 Upload CSV** — drag & drop any `.csv` file (auto-converted)
- **🐬 MySQL** — `mysql://user:pass@host:3306/dbname`
- **🐘 PostgreSQL** — `postgresql://user:pass@host:5432/dbname`
- **🗄 Demo DB** — built-in sample data

## CSV Example

Upload a file like `sales_data.csv`:
```
date,product,quantity,revenue
2024-01-01,Laptop,2,150000
2024-01-02,Phone,5,125000
```

QueryMind converts it to a SQLite table called `sales_data` and you can immediately ask:
- "What is the total revenue?"
- "Which product has the most sales?"
- "Show sales from January 2024"
