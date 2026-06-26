"""
auth.py – Role-Based Access Control for QueryMind
Roles: admin, user
Permissions: defined in ROLE_PERMISSIONS dict
"""

import sqlite3
import hashlib
from datetime import datetime
from functools import wraps
from flask import session, request, jsonify, redirect, url_for

# ── Permission definitions ────────────────────────────────────────
PERMISSIONS = {
    # Query permissions
    "query_select":        "Run SELECT queries",
    "query_insert":        "Run INSERT queries",
    "query_update":        "Run UPDATE queries",
    "query_delete":        "Run DELETE queries (admin only)",
    "query_drop":          "Run DROP statements (admin only)",
    "query_create":        "Run CREATE statements (admin only)",
    # Database management
    "db_connect":          "Connect to external databases",
    "db_upload":           "Upload database / CSV files",
    "db_reset":            "Reset to demo database",
    # ML controls
    "ml_train":            "Trigger ML model training",
    "ml_view_stats":       "View ML stats & clusters",
    # History & analytics
    "history_view":        "View own query history",
    "history_clear":       "Clear own query history",
    "history_view_all":    "View all users' history (admin only)",
    # Admin panel
    "admin_panel":         "Access admin panel",
    "admin_manage_users":  "Manage users (roles, ban, delete)",
    "admin_grant_perms":   "Grant/revoke permissions to users",
    "admin_view_logs":     "View system activity logs",
}

ROLE_PERMISSIONS = {
    "admin": set(PERMISSIONS.keys()),   # admin gets everything
    "user": {
        "query_select",
        "db_connect",
        "db_upload",
        "db_reset",
        "ml_view_stats",
        "history_view",
        "history_clear",
    },
}

# ── DB helpers ────────────────────────────────────────────────────
def get_auth_db():
    conn = sqlite3.connect("users.db")
    conn.row_factory = sqlite3.Row
    return conn

def init_auth_db():
    conn = get_auth_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            username    TEXT UNIQUE NOT NULL,
            email       TEXT UNIQUE NOT NULL,
            password    TEXT NOT NULL,
            role        TEXT NOT NULL DEFAULT 'user',
            is_active   INTEGER NOT NULL DEFAULT 1,
            created_at  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS user_permissions (
            user_id     INTEGER NOT NULL,
            permission  TEXT NOT NULL,
            granted_by  INTEGER,
            granted_at  TEXT NOT NULL,
            PRIMARY KEY (user_id, permission),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS permission_requests (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL,
            permission  TEXT NOT NULL,
            reason      TEXT,
            status      TEXT NOT NULL DEFAULT 'pending',
            reviewed_by INTEGER,
            reviewed_at TEXT,
            created_at  TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS activity_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER,
            username    TEXT,
            action      TEXT NOT NULL,
            detail      TEXT,
            ip_address  TEXT,
            timestamp   TEXT NOT NULL
        );
    """)

    # Migrate: add role/is_active columns if missing (for existing users.db)
    try:
        conn.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user'")
    except Exception:
        pass
    try:
        conn.execute("ALTER TABLE users ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1")
    except Exception:
        pass

    conn.commit()

    # Ensure at least one admin exists
    admin = conn.execute("SELECT id FROM users WHERE role='admin' LIMIT 1").fetchone()
    if not admin:
        # Promote first registered user to admin, or create default admin
        first = conn.execute("SELECT id FROM users ORDER BY id LIMIT 1").fetchone()
        if first:
            conn.execute("UPDATE users SET role='admin' WHERE id=?", (first["id"],))
            conn.commit()
        else:
            # Create default admin account
            conn.execute(
                "INSERT INTO users (username,email,password,role,is_active,created_at) VALUES (?,?,?,?,?,?)",
                ("admin", "admin@querymind.local", hash_password("admin123"), "admin", 1, datetime.now().isoformat())
            )
            conn.commit()

    conn.close()

def hash_password(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

# ── User CRUD ─────────────────────────────────────────────────────
def get_user_by_id(uid):
    conn = get_auth_db()
    r = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    conn.close()
    return r

def get_user_by_username(u):
    conn = get_auth_db()
    r = conn.execute("SELECT * FROM users WHERE username=?", (u,)).fetchone()
    conn.close()
    return r

def get_user_by_email(e):
    conn = get_auth_db()
    r = conn.execute("SELECT * FROM users WHERE email=?", (e,)).fetchone()
    conn.close()
    return r

def create_user(username, email, password, role="user"):
    conn = get_auth_db()
    conn.execute(
        "INSERT INTO users (username,email,password,role,is_active,created_at) VALUES (?,?,?,?,?,?)",
        (username, email, hash_password(password), role, 1, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()

def get_all_users():
    conn = get_auth_db()
    rows = conn.execute(
        "SELECT id,username,email,role,is_active,created_at FROM users ORDER BY id"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def update_user_role(uid, role):
    conn = get_auth_db()
    conn.execute("UPDATE users SET role=? WHERE id=?", (role, uid))
    conn.commit()
    conn.close()

def toggle_user_active(uid, is_active):
    conn = get_auth_db()
    conn.execute("UPDATE users SET is_active=? WHERE id=?", (is_active, uid))
    conn.commit()
    conn.close()

def delete_user(uid):
    conn = get_auth_db()
    conn.execute("DELETE FROM user_permissions WHERE user_id=?", (uid,))
    conn.execute("DELETE FROM permission_requests WHERE user_id=?", (uid,))
    conn.execute("DELETE FROM users WHERE id=?", (uid,))
    conn.commit()
    conn.close()

# ── Permission helpers ────────────────────────────────────────────
def get_user_permissions(user_id, role):
    """Returns effective permissions: role defaults + individually granted extras."""
    base = set(ROLE_PERMISSIONS.get(role, set()))
    conn = get_auth_db()
    extras = conn.execute(
        "SELECT permission FROM user_permissions WHERE user_id=?", (user_id,)
    ).fetchall()
    conn.close()
    extra_set = {r["permission"] for r in extras}
    return base | extra_set

def has_permission(user_id, role, perm):
    return perm in get_user_permissions(user_id, role)

def grant_permission(user_id, permission, granted_by_id):
    conn = get_auth_db()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO user_permissions (user_id,permission,granted_by,granted_at) VALUES (?,?,?,?)",
            (user_id, permission, granted_by_id, datetime.now().isoformat())
        )
        conn.commit()
    finally:
        conn.close()

def revoke_permission(user_id, permission):
    conn = get_auth_db()
    conn.execute(
        "DELETE FROM user_permissions WHERE user_id=? AND permission=?",
        (user_id, permission)
    )
    conn.commit()
    conn.close()

def get_user_extra_permissions(user_id):
    conn = get_auth_db()
    rows = conn.execute(
        "SELECT permission, granted_at FROM user_permissions WHERE user_id=?", (user_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ── Permission requests ───────────────────────────────────────────
def request_permission(user_id, permission, reason=""):
    conn = get_auth_db()
    # Don't duplicate pending requests
    existing = conn.execute(
        "SELECT id FROM permission_requests WHERE user_id=? AND permission=? AND status='pending'",
        (user_id, permission)
    ).fetchone()
    if existing:
        conn.close()
        return False, "A pending request already exists for this permission."
    conn.execute(
        "INSERT INTO permission_requests (user_id,permission,reason,status,created_at) VALUES (?,?,?,?,?)",
        (user_id, permission, reason, "pending", datetime.now().isoformat())
    )
    conn.commit()
    conn.close()
    return True, "Permission request submitted."

def get_pending_requests():
    conn = get_auth_db()
    rows = conn.execute("""
        SELECT pr.id, pr.user_id, u.username, pr.permission, pr.reason, pr.created_at
        FROM permission_requests pr
        JOIN users u ON pr.user_id = u.id
        WHERE pr.status = 'pending'
        ORDER BY pr.created_at DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_all_requests():
    conn = get_auth_db()
    rows = conn.execute("""
        SELECT pr.id, pr.user_id, u.username, pr.permission, pr.reason,
               pr.status, pr.reviewed_at, pr.created_at
        FROM permission_requests pr
        JOIN users u ON pr.user_id = u.id
        ORDER BY pr.created_at DESC LIMIT 100
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_my_requests(user_id):
    conn = get_auth_db()
    rows = conn.execute(
        "SELECT id, permission, reason, status, reviewed_at, created_at FROM permission_requests WHERE user_id=? ORDER BY created_at DESC",
        (user_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def review_request(request_id, status, reviewer_id):
    conn = get_auth_db()
    req = conn.execute("SELECT * FROM permission_requests WHERE id=?", (request_id,)).fetchone()
    if not req:
        conn.close()
        return False, "Request not found."
    conn.execute(
        "UPDATE permission_requests SET status=?, reviewed_by=?, reviewed_at=? WHERE id=?",
        (status, reviewer_id, datetime.now().isoformat(), request_id)
    )
    conn.commit()
    if status == "approved":
        try:
            conn.execute(
                "INSERT OR REPLACE INTO user_permissions (user_id,permission,granted_by,granted_at) VALUES (?,?,?,?)",
                (req["user_id"], req["permission"], reviewer_id, datetime.now().isoformat())
            )
            conn.commit()
        except Exception:
            pass
    conn.close()
    return True, f"Request {status}."

# ── Activity log ──────────────────────────────────────────────────
def log_action(user_id, username, action, detail="", ip=""):
    conn = get_auth_db()
    conn.execute(
        "INSERT INTO activity_log (user_id,username,action,detail,ip_address,timestamp) VALUES (?,?,?,?,?,?)",
        (user_id, username, action, detail, ip, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()

def get_activity_logs(limit=200):
    conn = get_auth_db()
    rows = conn.execute(
        "SELECT * FROM activity_log ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ── Flask decorators ──────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            if request.is_json or request.content_type == "application/json":
                return jsonify({"error": "Not authenticated", "redirect": "/login"}), 401
            return redirect(url_for("login_page"))
        user = get_user_by_id(session["user_id"])
        if not user or not user["is_active"]:
            session.clear()
            if request.is_json:
                return jsonify({"error": "Account suspended.", "redirect": "/login"}), 403
            return redirect(url_for("login_page"))
        return f(*args, **kwargs)
    return decorated

def permission_required(perm):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if "user_id" not in session:
                if request.is_json:
                    return jsonify({"error": "Not authenticated"}), 401
                return redirect(url_for("login_page"))
            uid  = session["user_id"]
            role = session.get("role", "user")
            if not has_permission(uid, role, perm):
                return jsonify({
                    "error": "Permission denied.",
                    "required_permission": perm,
                    "message": f"You need the '{PERMISSIONS.get(perm, perm)}' permission. Request it in Settings.",
                }), 403
            return f(*args, **kwargs)
        return decorated
    return permission_required

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get("role") != "admin":
            return jsonify({"error": "Admin access required."}), 403
        return f(*args, **kwargs)
    return decorated
