import os
import re
import time
import sqlite3
from functools import wraps
from datetime import datetime
from flask import Flask, request, jsonify, render_template, session, redirect, url_for
from groq import Groq
from werkzeug.utils import secure_filename

from database import init_db
from db_connector import (
    parse_connection_string, test_connection,
    execute_query, get_schema_for_prompt, conn_info_to_safe_dict
)
from history import QueryHistory
from csv_handler import file_to_sqlite, get_file_info, is_supported, csv_to_sqlite, get_csv_info
from auth import (
    init_auth_db, hash_password,
    get_user_by_username, get_user_by_email, get_user_by_id,
    create_user, get_all_users, update_user_role, toggle_user_active, delete_user,
    get_user_permissions, has_permission, grant_permission, revoke_permission,
    get_user_extra_permissions, request_permission, get_pending_requests,
    get_all_requests, get_my_requests, review_request,
    log_action, get_activity_logs,
    login_required, admin_required,
    PERMISSIONS, ROLE_PERMISSIONS,
)

app = Flask(__name__)
app.secret_key = "querymind-secret-key-change-in-production-2024"
app.config["UPLOAD_FOLDER"] = "uploads"
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024

os.makedirs("uploads", exist_ok=True)
os.makedirs("models",  exist_ok=True)

def _load_dotenv():
    """Load .env into os.environ if present (no extra dependency)."""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value

_load_dotenv()

def _get_groq_client():
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY is not set. Copy .env.example to .env and add your key, "
            "or run: $env:GROQ_API_KEY='your-key'  (PowerShell)"
        )
    return Groq(api_key=api_key)

try:
    client = _get_groq_client()
except RuntimeError as e:
    print(f"\n⚠  {e}\n")
    client = None

from ml.intent_classifier import get_classifier, get_intent_hint
from ml.success_predictor import get_predictor
from ml.query_suggester   import get_suggester

print("Initialising ML modules...")
_clf = get_classifier()
if not _clf.is_trained():
    _clf.train()
else:
    _clf.load()
get_predictor().load()
get_suggester().load()
print("ML modules ready")

user_connections = {}

SAMPLE_QUESTIONS = [
    "How many students are there?",
    "Show all students from Mumbai",
    "What is the average salary of employees?",
    "List all products with price greater than 10000",
    "How many employees are in each department?",
    "What is the highest score in enrollments?",
    "Show all delivered orders",
    "Which course has the most enrollments?",
    "Find employees earning more than 60000",
    "What is the total budget across all departments?",
]

DEMO_CONN = {"type": "sqlite", "path": "demo.db", "label": "demo.db"}

# Destructive SQL patterns
DESTRUCTIVE_PATTERNS = re.compile(
    r"^\s*(DELETE|DROP|TRUNCATE|ALTER\s+TABLE\s+\S+\s+DROP|CREATE\s+TABLE|INSERT|UPDATE)\b",
    re.IGNORECASE
)
DELETE_PATTERN  = re.compile(r"^\s*DELETE\b", re.IGNORECASE)
DROP_PATTERN    = re.compile(r"^\s*DROP\b",   re.IGNORECASE)
CREATE_PATTERN  = re.compile(r"^\s*(CREATE|ALTER)\b", re.IGNORECASE)
INSERT_PATTERN  = re.compile(r"^\s*INSERT\b", re.IGNORECASE)
UPDATE_PATTERN  = re.compile(r"^\s*UPDATE\b", re.IGNORECASE)

def get_sql_permission(sql):
    """Return the permission key required to run this SQL."""
    if DELETE_PATTERN.match(sql):   return "query_delete"
    if DROP_PATTERN.match(sql):     return "query_drop"
    if CREATE_PATTERN.match(sql):   return "query_create"
    if INSERT_PATTERN.match(sql):   return "query_insert"
    if UPDATE_PATTERN.match(sql):   return "query_update"
    return "query_select"

def get_conn_info():
    uid = session.get("user_id")
    return user_connections.get(uid, DEMO_CONN)

def set_conn_info(conn_info):
    uid = session.get("user_id")
    if uid:
        user_connections[uid] = conn_info

def perm_check(perm):
    """Return (allowed: bool, error_response | None)."""
    uid  = session.get("user_id")
    role = session.get("role", "user")
    if not has_permission(uid, role, perm):
        desc = PERMISSIONS.get(perm, perm)
        return False, jsonify({
            "error": "Permission denied.",
            "required_permission": perm,
            "message": f"You need '{desc}' permission. Request it in Settings → Permissions.",
        }), 403
    return True, None, None

# ── SQL generation ────────────────────────────────────────────────
def generate_sql(question, schema_str, db_type="sqlite", intent_hint=""):
    if client is None:
        raise RuntimeError(
            "Groq client not configured. Set GROQ_API_KEY in .env or your environment."
        )
    dialect = {"sqlite": "SQLite", "mysql": "MySQL", "postgresql": "PostgreSQL"}.get(db_type, "SQL")
    hint_block = f"\nHint: {intent_hint}" if intent_hint else ""
    prompt = f"""You are an expert {dialect} query generator.\n\nDatabase Schema:\n{schema_str}{hint_block}\n\nInstructions:\n- Write ONLY a single valid {dialect} SQL query\n- No explanations, no markdown, no code blocks\n- Use only tables and columns that exist in the schema above\n- End with a semicolon\n\nQuestion: {question}\nSQL:"""
    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=200, temperature=0)
    sql = response.choices[0].message.content.strip()
    sql = sql.replace("```sql","").replace("```","").strip()
    sql = sql.split(";")[0].strip() + ";"
    return sql

def explain_results(question, columns, rows):
    if not rows:
        return "No results were found for this query."
    prompt = f"""A user asked: "{question}"\nThe query returned {len(rows)} row(s). Columns: {columns}\nSample rows: {rows[:3]}\nWrite ONE clear sentence explaining the results. Do not mention SQL."""
    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=80, temperature=0.3)
    return response.choices[0].message.content.strip()

def validate_and_fix(sql, question, schema_str, conn_info):
    result = execute_query(conn_info, sql)
    if result["success"]:
        return {"success": True, "sql": sql, "rows": result["rows"],
                "columns": result["columns"], "attempts": 1, "fixed": False}
    error_msg = result.get("error", "unknown error")
    db_type   = conn_info.get("type", "sqlite")
    dialect   = {"sqlite":"SQLite","mysql":"MySQL","postgresql":"PostgreSQL"}.get(db_type,"SQL")
    fix_prompt = f"""This {dialect} query failed. Fix it.\n\nSchema:\n{schema_str}\n\nQuestion: {question}\nBroken SQL: {sql}\nError: {error_msg}\n\nOutput ONLY the corrected SQL query. No explanations. End with semicolon."""
    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "user", "content": fix_prompt}],
        max_tokens=200, temperature=0)
    fixed_sql = response.choices[0].message.content.strip()
    fixed_sql = fixed_sql.replace("```sql","").replace("```","").strip()
    fixed_sql = fixed_sql.split(";")[0].strip() + ";"
    result2 = execute_query(conn_info, fixed_sql)
    if result2["success"]:
        return {"success": True, "sql": fixed_sql, "rows": result2["rows"],
                "columns": result2["columns"], "attempts": 2, "fixed": True,
                "original_sql": sql, "original_error": error_msg}
    return {"success": False, "sql": fixed_sql, "rows": [], "columns": [],
            "attempts": 2, "fixed": False, "error": result2.get("error", ""),
            "original_sql": sql, "original_error": error_msg}

# ── Auth routes ───────────────────────────────────────────────────
@app.route("/login")
def login_page():
    if "user_id" in session:
        return redirect(url_for("index"))
    return render_template("login.html")

@app.route("/auth/login", methods=["POST"])
def auth_login():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = (data.get("password") or "").strip()
    if not username or not password:
        return jsonify({"error": "Username and password are required."}), 400
    user = get_user_by_username(username)
    if not user or user["password"] != hash_password(password):
        return jsonify({"error": "Invalid username or password."}), 401
    if not user["is_active"]:
        return jsonify({"error": "Your account has been suspended. Contact an admin."}), 403
    session["user_id"]  = user["id"]
    session["username"] = user["username"]
    session["role"]     = user["role"]
    session.permanent   = True
    log_action(user["id"], user["username"], "login", "", request.remote_addr)
    return jsonify({"success": True, "username": user["username"], "role": user["role"]})

@app.route("/auth/register", methods=["POST"])
def auth_register():
    data     = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    email    = (data.get("email")    or "").strip()
    password = (data.get("password") or "").strip()
    if not username or not email or not password:
        return jsonify({"error": "All fields are required."}), 400
    if len(username) < 3:
        return jsonify({"error": "Username must be at least 3 characters."}), 400
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters."}), 400
    if "@" not in email:
        return jsonify({"error": "Invalid email address."}), 400
    if get_user_by_username(username):
        return jsonify({"error": "Username already taken."}), 409
    if get_user_by_email(email):
        return jsonify({"error": "Email already registered."}), 409
    create_user(username, email, password, role="user")
    user = get_user_by_username(username)
    session["user_id"]  = user["id"]
    session["username"] = user["username"]
    session["role"]     = user["role"]
    session.permanent   = True
    log_action(user["id"], user["username"], "register", "", request.remote_addr)
    return jsonify({"success": True, "username": user["username"], "role": user["role"]})

@app.route("/auth/logout", methods=["POST"])
def auth_logout():
    uid = session.get("user_id")
    uname = session.get("username", "")
    if uid and uid in user_connections:
        del user_connections[uid]
    if uid:
        log_action(uid, uname, "logout", "", request.remote_addr)
    session.clear()
    return jsonify({"success": True})

@app.route("/auth/me")
@login_required
def auth_me():
    uid  = session["user_id"]
    role = session.get("role", "user")
    perms = list(get_user_permissions(uid, role))
    return jsonify({
        "user_id":     uid,
        "username":    session.get("username"),
        "role":        role,
        "permissions": perms,
        "is_admin":    role == "admin",
    })

# ── Main app routes ───────────────────────────────────────────────
@app.route("/")
@login_required
def index():
    conn_info = get_conn_info()
    try:
        _, display, _ = get_schema_for_prompt(conn_info)
    except Exception:
        display = "(could not load schema)"
    uid  = session["user_id"]
    role = session.get("role", "user")
    perms = list(get_user_permissions(uid, role))
    return render_template("index.html",
        samples=SAMPLE_QUESTIONS,
        schema=display,
        db_name=conn_info.get("label", "demo.db"),
        db_type=conn_info.get("type", "sqlite"),
        username=session.get("username", ""),
        role=role,
        permissions=perms,
        is_admin=(role == "admin"))

# ── Admin panel route ─────────────────────────────────────────────
@app.route("/admin")
@login_required
def admin_panel():
    if session.get("role") != "admin":
        return redirect(url_for("index"))
    return render_template("admin.html",
        username=session.get("username", ""),
        role="admin")

# ── DB connection routes ──────────────────────────────────────────
@app.route("/db/connect", methods=["POST"])
@login_required
def db_connect():
    uid  = session["user_id"]; role = session.get("role","user")
    if not has_permission(uid, role, "db_connect"):
        return jsonify({"error":"Permission denied. You need 'db_connect'."}), 403
    data     = request.get_json(silent=True) or {}
    conn_str = (data.get("conn_str") or "").strip()
    if not conn_str:
        return jsonify({"error": "Connection string is required."}), 400
    try:
        conn_info = parse_connection_string(conn_str)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    result = test_connection(conn_info)
    if not result["success"]:
        return jsonify({"error": result["message"]}), 400
    try:
        _, display, _ = get_schema_for_prompt(conn_info)
    except Exception as e:
        return jsonify({"error": f"Connected but could not read schema: {e}"}), 400
    set_conn_info(conn_info)
    log_action(uid, session.get("username"), "db_connect", conn_info.get("label",""))
    return jsonify({"success": True, "db_type": conn_info["type"],
                    "db_name": conn_info.get("label",""),
                    "tables": result["tables"], "schema": display,
                    "message": result["message"]})

@app.route("/db/upload", methods=["POST"])
@login_required
def db_upload():
    uid  = session["user_id"]; role = session.get("role","user")
    if not has_permission(uid, role, "db_upload"):
        return jsonify({"error":"Permission denied. You need 'db_upload'."}), 403
    file = request.files.get("database")
    if not file or not file.filename.endswith(".db"):
        return jsonify({"error": "Please upload a valid .db SQLite file."}), 400
    filename = secure_filename(file.filename)
    path     = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    file.save(path)
    conn_info = {"type": "sqlite", "path": os.path.abspath(path), "label": filename}
    result    = test_connection(conn_info)
    if not result["success"]:
        return jsonify({"error": result["message"]}), 400
    try:
        _, display, _ = get_schema_for_prompt(conn_info)
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    set_conn_info(conn_info)
    log_action(uid, session.get("username"), "db_upload", filename)
    return jsonify({"success": True, "db_type": "sqlite", "db_name": filename,
                    "tables": result["tables"], "schema": display})

@app.route("/db/preview-csv", methods=["POST"])
@login_required
def db_preview_csv():
    uid  = session["user_id"]; role = session.get("role","user")
    if not has_permission(uid, role, "db_upload"):
        return jsonify({"error":"Permission denied."}), 403
    file = request.files.get("csvfile")
    if not file or not is_supported(file.filename):
        return jsonify({"error": "Please upload a .csv, .xlsx, or .xls file."}), 400
    filename = secure_filename(file.filename)
    tmp_path = os.path.join(app.config["UPLOAD_FOLDER"], "__preview__" + filename)
    file.save(tmp_path)
    delimiter = request.form.get("delimiter", "").strip() or None
    try:
        info = get_file_info(tmp_path, delimiter=delimiter)
        if "error" in info:
            return jsonify({"error": info["error"]}), 400
        return jsonify(info)
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

@app.route("/db/upload-csv", methods=["POST"])
@login_required
def db_upload_csv():
    uid  = session["user_id"]; role = session.get("role","user")
    if not has_permission(uid, role, "db_upload"):
        return jsonify({"error":"Permission denied."}), 403
    file = request.files.get("csvfile")
    if not file or not is_supported(file.filename):
        return jsonify({"error": "Please upload a .csv, .xlsx, or .xls file."}), 400
    filename  = secure_filename(file.filename)
    file_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    file.save(file_path)
    table_name = request.form.get("table_name","").strip() or None
    delimiter  = request.form.get("delimiter","").strip() or None
    sheet_name = request.form.get("sheet_name","").strip() or None
    try:
        conn_info, preview = file_to_sqlite(file_path, table_name=table_name,
                                             output_dir=app.config["UPLOAD_FOLDER"],
                                             delimiter=delimiter, sheet_name=sheet_name)
    except Exception as e:
        return jsonify({"error": f"Could not parse file: {str(e)}"}), 400
    try:
        _, schema_display, _ = get_schema_for_prompt(conn_info)
    except Exception as e:
        schema_display = preview.get("schema_display","")
    set_conn_info(conn_info)
    log_action(uid, session.get("username"), "csv_upload", filename)
    return jsonify({"success": True, "db_type": "sqlite",
                    "db_name": conn_info["label"], "source": "csv",
                    "table_name": preview["table_name"], "columns": preview["columns"],
                    "col_types": preview["col_types"], "total_rows": preview["total_rows"],
                    "skipped_rows": preview["skipped_rows"], "delimiter": preview["delimiter"],
                    "preview_rows": preview["preview_rows"], "schema": schema_display})

@app.route("/db/reset", methods=["POST"])
@login_required
def db_reset():
    uid  = session["user_id"]; role = session.get("role","user")
    if not has_permission(uid, role, "db_reset"):
        return jsonify({"error":"Permission denied."}), 403
    set_conn_info(DEMO_CONN)
    try:
        _, display, _ = get_schema_for_prompt(DEMO_CONN)
    except Exception:
        display = ""
    return jsonify({"success": True, "schema": display, "db_name": "demo.db", "db_type": "sqlite"})

@app.route("/db/test", methods=["POST"])
@login_required
def db_test():
    uid  = session["user_id"]; role = session.get("role","user")
    if not has_permission(uid, role, "db_connect"):
        return jsonify({"error":"Permission denied."}), 403
    data     = request.get_json(silent=True) or {}
    conn_str = (data.get("conn_str") or "").strip()
    if not conn_str:
        return jsonify({"error": "Connection string is required."}), 400
    try:
        conn_info = parse_connection_string(conn_str)
        result    = test_connection(conn_info)
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route("/db/schema")
@login_required
def db_schema():
    conn_info = get_conn_info()
    try:
        _, display, _ = get_schema_for_prompt(conn_info)
        return jsonify({"schema": display, "db_name": conn_info.get("label",""),
                        "db_type": conn_info.get("type","sqlite")})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ── Query routes with permission checks ───────────────────────────
@app.route("/query", methods=["POST"])
@login_required
def query():
    conn_info = get_conn_info()
    history   = QueryHistory(session["user_id"])
    data      = request.get_json(silent=True) or {}
    question  = data.get("question", "").strip()
    if not question:
        return jsonify({"error": "Please enter a question."}), 400
    start = time.time()
    try:
        intent_hint, intent_result = get_intent_hint(question)
        intent        = intent_result["intent"]
        intent_conf   = intent_result["confidence"]
        intent_scores = intent_result["scores"]
        try:
            _, _, schema_dict = get_schema_for_prompt(conn_info)
            table_count = len(schema_dict)
        except Exception:
            table_count = 5
        pred_result = get_predictor().predict(question, intent_scores, table_count)
        suggestions = get_suggester().suggest(question, top_k=3)
        try:
            schema_str, _, _ = get_schema_for_prompt(conn_info)
        except Exception as e:
            return jsonify({"error": f"Could not read database schema: {e}"}), 500
        db_type = conn_info.get("type", "sqlite")
        sql = generate_sql(question, schema_str, db_type, intent_hint)

        # Permission check on generated SQL
        required_perm = get_sql_permission(sql)
        uid  = session["user_id"]; role = session.get("role","user")
        if not has_permission(uid, role, required_perm):
            desc = PERMISSIONS.get(required_perm, required_perm)
            return jsonify({
                "error": "Permission denied.",
                "required_permission": required_perm,
                "message": f"Your question maps to a {required_perm.split('_')[1].upper()} query which requires '{desc}'. Request access in Settings.",
                "sql": sql,
            }), 403

        result = validate_and_fix(sql, question, schema_str, conn_info)
        response_ms = int((time.time() - start) * 1000)
        ml_payload = {"intent": intent, "intent_conf": intent_conf,
                      "prediction": pred_result, "suggestions": suggestions}
        db_label = conn_info.get("label", "demo.db")
        if not result["success"]:
            history.log(question, result["sql"], False, result["attempts"], False, 0, response_ms, db_label)
            get_predictor().maybe_retrain(session["user_id"])
            return jsonify({"success": False, "error": result["error"], "sql": result["sql"],
                            "response_ms": response_ms, "ml": ml_payload}), 200
        explanation = explain_results(question, result["columns"], result["rows"])
        history.log(question, result["sql"], True, result["attempts"], result["fixed"],
                    len(result["rows"]), response_ms, db_label)
        get_predictor().maybe_retrain(session["user_id"])
        get_suggester().fit(session["user_id"])
        log_action(uid, session.get("username"), "query", question[:100])
        return jsonify({"success": True, "question": question, "sql": result["sql"],
                        "columns": result["columns"], "rows": result["rows"],
                        "row_count": len(result["rows"]), "explanation": explanation,
                        "response_ms": response_ms, "fixed": result["fixed"],
                        "attempts": result["attempts"],
                        "original_sql": result.get("original_sql",""), "ml": ml_payload})
    except Exception as e:
        response_ms = int((time.time() - start) * 1000)
        history.log(question, "", False, 1, False, 0, response_ms, "error")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/generate", methods=["POST"])
@login_required
def generate():
    conn_info = get_conn_info()
    data      = request.get_json(silent=True) or {}
    question  = data.get("question", "").strip()
    if not question:
        return jsonify({"error": "Please enter a question."}), 400
    start = time.time()
    try:
        intent_hint, intent_result = get_intent_hint(question)
        intent        = intent_result["intent"]
        intent_conf   = intent_result["confidence"]
        intent_scores = intent_result["scores"]
        try:
            _, _, schema_dict = get_schema_for_prompt(conn_info)
            table_count = len(schema_dict)
        except Exception:
            table_count = 5
        pred_result = get_predictor().predict(question, intent_scores, table_count)
        suggestions = get_suggester().suggest(question, top_k=3)
        try:
            schema_str, _, _ = get_schema_for_prompt(conn_info)
        except Exception as e:
            return jsonify({"error": f"Could not read database schema: {e}"}), 500
        db_type = conn_info.get("type", "sqlite")
        sql = generate_sql(question, schema_str, db_type, intent_hint)
        gen_ms = int((time.time() - start) * 1000)

        # Tell UI whether this SQL is allowed
        required_perm = get_sql_permission(sql)
        uid  = session["user_id"]; role = session.get("role","user")
        allowed = has_permission(uid, role, required_perm)

        return jsonify({"success": True, "question": question, "sql": sql,
                        "gen_ms": gen_ms, "allowed": allowed,
                        "required_permission": required_perm,
                        "ml": {"intent": intent, "intent_conf": intent_conf,
                               "prediction": pred_result, "suggestions": suggestions}})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/execute", methods=["POST"])
@login_required
def execute():
    conn_info = get_conn_info()
    history   = QueryHistory(session["user_id"])
    data      = request.get_json(silent=True) or {}
    sql       = data.get("sql", "").strip()
    question  = data.get("question", "").strip()
    if not sql:
        return jsonify({"error": "No SQL provided."}), 400

    # Permission check
    required_perm = get_sql_permission(sql)
    uid  = session["user_id"]; role = session.get("role","user")
    if not has_permission(uid, role, required_perm):
        desc = PERMISSIONS.get(required_perm, required_perm)
        return jsonify({
            "error": "Permission denied.",
            "required_permission": required_perm,
            "message": f"Executing this SQL requires '{desc}'. Request access in Settings → Permissions.",
        }), 403

    start = time.time()
    try:
        try:
            schema_str, _, _ = get_schema_for_prompt(conn_info)
        except Exception as e:
            return jsonify({"error": f"Could not read database schema: {e}"}), 500
        result = validate_and_fix(sql, question, schema_str, conn_info)
        exec_ms = int((time.time() - start) * 1000)
        db_label = conn_info.get("label", "demo.db")
        if not result["success"]:
            history.log(question or sql, result["sql"], False, result["attempts"],
                        False, 0, exec_ms, db_label)
            get_predictor().maybe_retrain(session["user_id"])
            return jsonify({"success": False, "error": result["error"],
                            "sql": result["sql"], "exec_ms": exec_ms,
                            "fixed": False, "attempts": result["attempts"],
                            "original_sql": result.get("original_sql","")}), 200
        explanation = explain_results(question or sql, result["columns"], result["rows"])
        history.log(question or sql, result["sql"], True, result["attempts"],
                    result["fixed"], len(result["rows"]), exec_ms, db_label)
        get_predictor().maybe_retrain(session["user_id"])
        get_suggester().fit(session["user_id"])
        log_action(uid, session.get("username"), "execute", (question or sql)[:100])
        return jsonify({"success": True, "sql": result["sql"],
                        "columns": result["columns"], "rows": result["rows"],
                        "row_count": len(result["rows"]), "explanation": explanation,
                        "exec_ms": exec_ms, "fixed": result["fixed"],
                        "attempts": result["attempts"],
                        "original_sql": result.get("original_sql","")})
    except Exception as e:
        exec_ms = int((time.time() - start) * 1000)
        history.log(question or sql, "", False, 1, False, 0, exec_ms, "error")
        return jsonify({"success": False, "error": str(e)}), 500

# ── ML routes ─────────────────────────────────────────────────────
@app.route("/ml/intent", methods=["POST"])
@login_required
def ml_intent():
    data = request.get_json(silent=True) or {}
    q    = data.get("question","").strip()
    if not q:
        return jsonify({"intent":"","confidence":0,"scores":{}})
    _, result = get_intent_hint(q)
    return jsonify(result)

@app.route("/ml/suggest", methods=["POST"])
@login_required
def ml_suggest():
    data = request.get_json(silent=True) or {}
    q    = data.get("question","").strip()
    if not q:
        return jsonify({"suggestions":[]})
    return jsonify({"suggestions": get_suggester().suggest(q, top_k=3)})

@app.route("/ml/train", methods=["POST"])
@login_required
def ml_train():
    uid  = session["user_id"]; role = session.get("role","user")
    if not has_permission(uid, role, "ml_train"):
        return jsonify({"error":"Admin permission required to train models."}), 403
    results = {}
    results["intent_classifier"] = get_classifier().train()
    pred = get_predictor().train(session["user_id"])
    results["success_predictor"] = pred or "Not enough data (need 10+ queries)"
    sug_ok = get_suggester().fit(session["user_id"])
    results["query_suggester"] = "fitted" if sug_ok else "Not enough data (need 3+ queries)"
    log_action(uid, session.get("username"), "ml_train", "")
    return jsonify({"success": True, "results": results})

@app.route("/ml/stats")
@login_required
def ml_stats():
    uid  = session["user_id"]; role = session.get("role","user")
    if not has_permission(uid, role, "ml_view_stats"):
        return jsonify({"error":"Permission denied."}), 403
    clf  = get_classifier()
    pred = get_predictor()
    sug  = get_suggester()
    return jsonify({
        "intent_classifier": {"trained": clf.is_trained(), "classes": clf.classes_},
        "success_predictor": {"trained": pred.is_trained(),
                              "feature_importance": pred.get_feature_importance()[:8]},
        "query_suggester":   {"ready": sug.is_ready(), "questions": len(sug.questions)},
    })

@app.route("/ml/clusters")
@login_required
def ml_clusters():
    return jsonify({"clusters": get_suggester().cluster_queries(session["user_id"], n_clusters=5)})

# ── Permission request routes ─────────────────────────────────────
@app.route("/permissions/request", methods=["POST"])
@login_required
def req_permission():
    data  = request.get_json(silent=True) or {}
    perm  = data.get("permission","").strip()
    reason = data.get("reason","").strip()
    if perm not in PERMISSIONS:
        return jsonify({"error":"Unknown permission."}), 400
    uid  = session["user_id"]; role = session.get("role","user")
    # Already have it?
    if has_permission(uid, role, perm):
        return jsonify({"error":"You already have this permission."}), 400
    ok, msg = request_permission(uid, perm, reason)
    log_action(uid, session.get("username"), "permission_request", perm)
    return jsonify({"success": ok, "message": msg})

@app.route("/permissions/my-requests")
@login_required
def my_requests():
    return jsonify({"requests": get_my_requests(session["user_id"])})

@app.route("/permissions/available")
@login_required
def available_permissions():
    uid  = session["user_id"]; role = session.get("role","user")
    current = get_user_permissions(uid, role)
    result = []
    for key, desc in PERMISSIONS.items():
        result.append({
            "key": key,
            "description": desc,
            "granted": key in current,
            "is_role_default": key in ROLE_PERMISSIONS.get(role, set()),
        })
    return jsonify({"permissions": result, "role": role})

# ── Admin API routes ──────────────────────────────────────────────
@app.route("/admin/users")
@login_required
@admin_required
def admin_users():
    users = get_all_users()
    for u in users:
        u["permissions"] = get_user_extra_permissions(u["id"])
    return jsonify({"users": users})

@app.route("/admin/users/<int:uid>/role", methods=["POST"])
@login_required
@admin_required
def admin_set_role(uid):
    data = request.get_json(silent=True) or {}
    role = data.get("role","")
    if role not in ("admin","user"):
        return jsonify({"error":"Role must be 'admin' or 'user'."}), 400
    if uid == session["user_id"]:
        return jsonify({"error":"Cannot change your own role."}), 400
    update_user_role(uid, role)
    log_action(session["user_id"], session.get("username"), "set_role", f"uid={uid} role={role}")
    return jsonify({"success": True})

@app.route("/admin/users/<int:uid>/toggle", methods=["POST"])
@login_required
@admin_required
def admin_toggle_user(uid):
    if uid == session["user_id"]:
        return jsonify({"error":"Cannot suspend yourself."}), 400
    data = request.get_json(silent=True) or {}
    is_active = int(bool(data.get("is_active", True)))
    toggle_user_active(uid, is_active)
    action = "activate_user" if is_active else "suspend_user"
    log_action(session["user_id"], session.get("username"), action, f"uid={uid}")
    return jsonify({"success": True})

@app.route("/admin/users/<int:uid>/delete", methods=["POST"])
@login_required
@admin_required
def admin_delete_user(uid):
    if uid == session["user_id"]:
        return jsonify({"error":"Cannot delete yourself."}), 400
    delete_user(uid)
    log_action(session["user_id"], session.get("username"), "delete_user", f"uid={uid}")
    return jsonify({"success": True})

@app.route("/admin/users/<int:uid>/grant", methods=["POST"])
@login_required
@admin_required
def admin_grant(uid):
    data = request.get_json(silent=True) or {}
    perm = data.get("permission","")
    if perm not in PERMISSIONS:
        return jsonify({"error":"Unknown permission."}), 400
    grant_permission(uid, perm, session["user_id"])
    log_action(session["user_id"], session.get("username"), "grant_permission", f"uid={uid} perm={perm}")
    return jsonify({"success": True})

@app.route("/admin/users/<int:uid>/revoke", methods=["POST"])
@login_required
@admin_required
def admin_revoke(uid):
    data = request.get_json(silent=True) or {}
    perm = data.get("permission","")
    revoke_permission(uid, perm)
    log_action(session["user_id"], session.get("username"), "revoke_permission", f"uid={uid} perm={perm}")
    return jsonify({"success": True})

@app.route("/admin/requests")
@login_required
@admin_required
def admin_requests():
    return jsonify({
        "pending": get_pending_requests(),
        "all":     get_all_requests()
    })

@app.route("/admin/requests/<int:req_id>/review", methods=["POST"])
@login_required
@admin_required
def admin_review(req_id):
    data   = request.get_json(silent=True) or {}
    status = data.get("status","")
    if status not in ("approved","rejected"):
        return jsonify({"error":"Status must be 'approved' or 'rejected'."}), 400
    ok, msg = review_request(req_id, status, session["user_id"])
    log_action(session["user_id"], session.get("username"), f"review_request_{status}", f"req_id={req_id}")
    return jsonify({"success": ok, "message": msg})

@app.route("/admin/logs")
@login_required
@admin_required
def admin_logs():
    return jsonify({"logs": get_activity_logs(300)})

@app.route("/admin/history")
@login_required
@admin_required
def admin_all_history():
    uid  = session["user_id"]; role = session.get("role","user")
    if not has_permission(uid, role, "history_view_all"):
        return jsonify({"error":"Permission denied."}), 403
    import sqlite3 as _sq
    conn = _sq.connect("history.db")
    conn.row_factory = _sq.Row
    rows = conn.execute(
        "SELECT h.*, u.username FROM history h LEFT JOIN users u ON h.user_id=u.id ORDER BY h.id DESC LIMIT 200"
    ).fetchall()
    conn.close()
    return jsonify({"history": [dict(r) for r in rows]})

# ── Analytics / history routes ────────────────────────────────────
@app.route("/analytics")
@login_required
def analytics():
    return jsonify(QueryHistory(session["user_id"]).get_stats())

@app.route("/clear-history", methods=["POST"])
@login_required
def clear_history():
    uid  = session["user_id"]; role = session.get("role","user")
    if not has_permission(uid, role, "history_clear"):
        return jsonify({"error":"Permission denied."}), 403
    QueryHistory(session["user_id"]).clear()
    return jsonify({"success": True})

# ── Start ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    init_db()
    init_auth_db()
    print("\n QueryMind ML (RBAC) running at http://localhost:5000\n")
    app.run(debug=True, port=5000)
