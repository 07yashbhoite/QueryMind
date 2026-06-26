"""
db_connector.py
================
Handles all database connection types:

  1. SQLite — demo.db (built-in)
  2. SQLite — file upload (.db file uploaded via browser)
  3. SQLite — local path (user types full path to their .db file)
  4. MySQL  — connection string (mysql://user:pass@host:port/dbname)
  5. PostgreSQL — connection string (postgresql://user:pass@host:port/dbname)

The rest of the app always calls get_connection(conn_info) and gets back
a standard connection object. All SQL execution goes through execute_query().
"""

import os
import sqlite3
from urllib.parse import urlparse


# ── Connection info dict structure ────────────────────────────────
# {
#   "type":     "sqlite" | "mysql" | "postgresql",
#   "path":     "/absolute/path/to/file.db"       (sqlite only)
#   "host":     "localhost",
#   "port":     3306,
#   "user":     "root",
#   "password": "secret",
#   "database": "mydb",
#   "label":    "My Production DB"   (display name)
# }


def parse_connection_string(conn_str: str) -> dict:
    """
    Parse a connection string into a conn_info dict.

    Supported formats:
      sqlite:///path/to/file.db
      sqlite:////absolute/path/to/file.db
      /absolute/path/to/file.db          (raw path — assumed SQLite)
      C:\\Users\\name\\file.db            (Windows path — SQLite)
      mysql://user:pass@host:3306/dbname
      postgresql://user:pass@host:5432/dbname
      postgres://user:pass@host:5432/dbname
    """
    conn_str = conn_str.strip()

    # Raw file path (SQLite)
    if conn_str.startswith("/") or (len(conn_str) > 2 and conn_str[1] == ":"):
        return {
            "type":  "sqlite",
            "path":  conn_str,
            "label": os.path.basename(conn_str),
        }

    parsed = urlparse(conn_str)
    scheme = parsed.scheme.lower()

    # sqlite:// URLs
    if scheme in ("sqlite", "sqlite3"):
        # sqlite:///relative.db  →  relative.db
        # sqlite:////abs/path.db →  /abs/path.db
        path = parsed.path
        if not path:
            raise ValueError("SQLite URL must include a file path. Example: sqlite:///mydb.db")
        return {
            "type":  "sqlite",
            "path":  path,
            "label": os.path.basename(path),
        }

    # MySQL
    if scheme in ("mysql", "mysql+pymysql", "mysql+mysqlconnector"):
        return {
            "type":     "mysql",
            "host":     parsed.hostname or "localhost",
            "port":     parsed.port or 3306,
            "user":     parsed.username or "root",
            "password": parsed.password or "",
            "database": parsed.path.lstrip("/"),
            "label":    f"{parsed.hostname}/{parsed.path.lstrip('/')}",
        }

    # PostgreSQL
    if scheme in ("postgresql", "postgres", "postgresql+psycopg2"):
        return {
            "type":     "postgresql",
            "host":     parsed.hostname or "localhost",
            "port":     parsed.port or 5432,
            "user":     parsed.username or "postgres",
            "password": parsed.password or "",
            "database": parsed.path.lstrip("/"),
            "label":    f"{parsed.hostname}/{parsed.path.lstrip('/')}",
        }

    raise ValueError(
        f"Unsupported connection type '{scheme}'. "
        "Use a file path, sqlite://, mysql://, or postgresql:// URL."
    )


def test_connection(conn_info: dict) -> dict:
    """
    Test that a connection works without running any queries.
    Returns {"success": True, "tables": [...], "message": "..."}
    """
    try:
        conn = get_connection(conn_info)
        tables = list_tables(conn, conn_info["type"])
        conn.close()
        return {
            "success": True,
            "tables":  tables,
            "message": f"Connected successfully. Found {len(tables)} table(s).",
        }
    except Exception as e:
        return {"success": False, "message": str(e)}


def get_connection(conn_info: dict):
    """Return a live DB connection object for any supported type."""
    db_type = conn_info.get("type", "sqlite")

    if db_type == "sqlite":
        path = conn_info["path"]
        if not os.path.isabs(path):
            # Relative paths are resolved from the project root
            path = os.path.abspath(path)
        if not os.path.exists(path):
            raise FileNotFoundError(
                f"SQLite file not found: {path}\n"
                "Check the path is correct and the file exists."
            )
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        return conn

    if db_type == "mysql":
        try:
            import pymysql
        except ImportError:
            raise ImportError(
                "PyMySQL is not installed.\n"
                "Run:  pip install pymysql"
            )
        return pymysql.connect(
            host=conn_info["host"],
            port=int(conn_info["port"]),
            user=conn_info["user"],
            password=conn_info["password"],
            database=conn_info["database"],
            cursorclass=pymysql.cursors.DictCursor,
            connect_timeout=10,
        )

    if db_type == "postgresql":
        try:
            import psycopg2
            import psycopg2.extras
        except ImportError:
            raise ImportError(
                "psycopg2 is not installed.\n"
                "Run:  pip install psycopg2-binary"
            )
        return psycopg2.connect(
            host=conn_info["host"],
            port=int(conn_info["port"]),
            user=conn_info["user"],
            password=conn_info["password"],
            dbname=conn_info["database"],
            connect_timeout=10,
        )

    raise ValueError(f"Unknown database type: {db_type}")


def list_tables(conn, db_type: str) -> list:
    """Return list of table names for any DB type."""
    cur = conn.cursor()

    if db_type == "sqlite":
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
        return [row[0] for row in cur.fetchall()]

    if db_type == "mysql":
        cur.execute("SHOW TABLES")
        rows = cur.fetchall()
        # pymysql DictCursor returns dicts
        if rows and isinstance(rows[0], dict):
            return [list(r.values())[0] for r in rows]
        return [r[0] for r in rows]

    if db_type == "postgresql":
        cur.execute("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
            ORDER BY table_name
        """)
        return [row[0] for row in cur.fetchall()]

    return []


def execute_query(conn_info: dict, sql: str) -> dict:
    """
    Execute a SQL query and return results.
    Returns {"success": True, "columns": [...], "rows": [[...], ...]}
    """
    conn = None
    try:
        conn    = get_connection(conn_info)
        db_type = conn_info.get("type", "sqlite")

        if db_type == "sqlite":
            cur = conn.cursor()
            cur.execute(sql)
            rows    = cur.fetchall()
            columns = [d[0] for d in cur.description] if cur.description else []
            return {
                "success": True,
                "columns": columns,
                "rows":    [list(r) for r in rows],
            }

        if db_type == "mysql":
            import pymysql
            with conn.cursor() as cur:
                cur.execute(sql)
                rows    = cur.fetchall()
                columns = [d[0] for d in cur.description] if cur.description else []
                # DictCursor returns dicts — extract values in column order
                if rows and isinstance(rows[0], dict):
                    return {
                        "success": True,
                        "columns": columns,
                        "rows":    [[r[c] for c in columns] for r in rows],
                    }
                return {"success": True, "columns": columns, "rows": [list(r) for r in rows]}

        if db_type == "postgresql":
            cur = conn.cursor()
            cur.execute(sql)
            rows    = cur.fetchall()
            columns = [d[0] for d in cur.description] if cur.description else []
            return {"success": True, "columns": columns, "rows": [list(r) for r in rows]}

    except Exception as e:
        return {"success": False, "error": str(e), "columns": [], "rows": []}
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


def get_schema_for_prompt(conn_info: dict) -> tuple[str, str, dict]:
    """
    Extract schema from any DB type.
    Returns (prompt_string, display_string, schema_dict)
    """
    db_type = conn_info.get("type", "sqlite")

    try:
        conn   = get_connection(conn_info)
        tables = list_tables(conn, db_type)
        conn.close()
    except Exception as e:
        raise ConnectionError(f"Could not connect: {e}")

    schema_dict  = {}
    prompt_lines = []
    display_lines = []

    for table in tables:
        try:
            conn = get_connection(conn_info)
            cur  = conn.cursor()

            # Get columns
            if db_type == "sqlite":
                cur.execute(f"PRAGMA table_info({table})")
                cols = [(row[1], row[2]) for row in cur.fetchall()]
            elif db_type == "mysql":
                cur.execute(f"DESCRIBE `{table}`")
                rows = cur.fetchall()
                if rows and isinstance(rows[0], dict):
                    cols = [(r["Field"], r["Type"]) for r in rows]
                else:
                    cols = [(r[0], r[1]) for r in rows]
            elif db_type == "postgresql":
                cur.execute("""
                    SELECT column_name, data_type
                    FROM information_schema.columns
                    WHERE table_name = %s AND table_schema = 'public'
                    ORDER BY ordinal_position
                """, (table,))
                cols = [(r[0], r[1]) for r in cur.fetchall()]
            else:
                cols = []

            # Get row count
            try:
                if db_type == "mysql":
                    cur.execute(f"SELECT COUNT(*) as cnt FROM `{table}`")
                elif db_type == "postgresql":
                    cur.execute(f'SELECT COUNT(*) FROM "{table}"')
                else:
                    cur.execute(f"SELECT COUNT(*) FROM {table}")
                count_row = cur.fetchone()
                count = count_row[0] if not isinstance(count_row, dict) else count_row.get("cnt", 0)
            except Exception:
                count = 0

            # Get sample row
            try:
                if db_type == "mysql":
                    cur.execute(f"SELECT * FROM `{table}` LIMIT 1")
                elif db_type == "postgresql":
                    cur.execute(f'SELECT * FROM "{table}" LIMIT 1')
                else:
                    cur.execute(f"SELECT * FROM {table} LIMIT 1")
                sample = cur.fetchone()
                if sample and isinstance(sample, dict):
                    sample = tuple(sample.values())
            except Exception:
                sample = None

            conn.close()

            schema_dict[table] = {"columns": cols, "row_count": count}

            col_str = ", ".join(f"{c[0]}({c[1]})" for c in cols)
            prompt_lines.append(f"Table '{table}' ({count} rows): {col_str}")
            if sample:
                prompt_lines.append(f"  Sample row: {sample}")

            col_names = ", ".join(c[0] for c in cols)
            display_lines.append(f"{table}({col_names})")

        except Exception as e:
            display_lines.append(f"{table}(error: {e})")
            continue

    return "\n".join(prompt_lines), "\n".join(display_lines), schema_dict


def conn_info_to_safe_dict(conn_info: dict) -> dict:
    """Return conn_info without password — safe to send to frontend."""
    safe = {k: v for k, v in conn_info.items() if k != "password"}
    return safe
