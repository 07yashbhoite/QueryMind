import sqlite3
from datetime import datetime


class QueryHistory:
    def __init__(self, user_id: int = None):
        self.user_id = user_id
        conn = sqlite3.connect("history.db")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS history (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id      INTEGER,
                question     TEXT,
                sql          TEXT,
                success      INTEGER,
                attempts     INTEGER,
                fixed        INTEGER,
                row_count    INTEGER,
                response_ms  INTEGER,
                db_used      TEXT,
                timestamp    TEXT
            )
        """)
        conn.commit()
        conn.close()

    def log(self, question, sql, success, attempts, fixed, row_count, response_ms, db_used="demo.db"):
        conn = sqlite3.connect("history.db")
        conn.execute("""
            INSERT INTO history
                (user_id, question, sql, success, attempts, fixed, row_count, response_ms, db_used, timestamp)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (self.user_id, question, sql, int(success), attempts, int(fixed),
              row_count, response_ms, db_used, datetime.now().isoformat()))
        conn.commit()
        conn.close()

    def get_stats(self) -> dict:
        conn = sqlite3.connect("history.db")
        cur = conn.cursor()

        if self.user_id:
            cur.execute("""
                SELECT
                    COUNT(*)                                  AS total,
                    SUM(success)                              AS successful,
                    ROUND(AVG(response_ms))                   AS avg_ms,
                    SUM(CASE WHEN fixed=1 THEN 1 ELSE 0 END) AS self_corrected
                FROM history WHERE user_id = ?
            """, (self.user_id,))
        else:
            cur.execute("""
                SELECT
                    COUNT(*)                                  AS total,
                    SUM(success)                              AS successful,
                    ROUND(AVG(response_ms))                   AS avg_ms,
                    SUM(CASE WHEN fixed=1 THEN 1 ELSE 0 END) AS self_corrected
                FROM history
            """)

        row = cur.fetchone()
        total      = row[0] or 0
        successful = row[1] or 0

        if self.user_id:
            cur.execute("""
                SELECT question, sql, success, fixed, timestamp
                FROM history WHERE user_id = ?
                ORDER BY id DESC LIMIT 20
            """, (self.user_id,))
        else:
            cur.execute("""
                SELECT question, sql, success, fixed, timestamp
                FROM history ORDER BY id DESC LIMIT 20
            """)

        recent = [
            {
                "question":  r[0],
                "sql":       r[1],
                "success":   bool(r[2]),
                "fixed":     bool(r[3]),
                "timestamp": r[4][:19].replace("T", " ")
            }
            for r in cur.fetchall()
        ]

        conn.close()
        return {
            "total":          total,
            "successful":     successful,
            "failed":         total - successful,
            "accuracy":       round(successful / total * 100, 1) if total else 0,
            "avg_ms":         row[2] or 0,
            "self_corrected": row[3] or 0,
            "recent":         recent
        }

    def clear(self):
        conn = sqlite3.connect("history.db")
        if self.user_id:
            conn.execute("DELETE FROM history WHERE user_id = ?", (self.user_id,))
        else:
            conn.execute("DELETE FROM history")
        conn.commit()
        conn.close()
