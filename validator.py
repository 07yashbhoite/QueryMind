import sqlite3


class SQLValidator:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def validate_and_fix(self, sql: str, question: str, schema_str: str, client) -> dict:
        """Tries to run SQL — if it fails, asks LLM to fix it automatically."""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        # First attempt
        try:
            cur.execute(sql)
            rows    = cur.fetchall()
            columns = [d[0] for d in cur.description]
            conn.close()
            return {
                "success": True,
                "sql":     sql,
                "rows":    [list(r) for r in rows],
                "columns": columns,
                "attempts": 1,
                "fixed":   False
            }
        except Exception as e:
            error_msg = str(e)

        conn.close()

        # Self-correction — ask LLM to fix its own mistake
        fix_prompt = f"""This SQL query failed with an error. Fix it.

Database Schema:
{schema_str}

Original question: {question}
Broken SQL: {sql}
Error: {error_msg}

Rules:
- Output ONLY the corrected raw SQL query
- No explanations, no markdown, no code blocks
- Must be valid SQLite syntax

Corrected SQL:"""

        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": fix_prompt}],
            max_tokens=150,
            temperature=0,
        )
        fixed_sql = response.choices[0].message.content.strip()
        fixed_sql = fixed_sql.replace("```sql", "").replace("```", "").strip()
        fixed_sql = fixed_sql.split(";")[0].strip() + ";"

        # Second attempt with fixed SQL
        conn2 = sqlite3.connect(self.db_path)
        cur2  = conn2.cursor()
        try:
            cur2.execute(fixed_sql)
            rows    = cur2.fetchall()
            columns = [d[0] for d in cur2.description]
            conn2.close()
            return {
                "success":        True,
                "sql":            fixed_sql,
                "rows":           [list(r) for r in rows],
                "columns":        columns,
                "attempts":       2,
                "fixed":          True,
                "original_sql":   sql,
                "original_error": error_msg
            }
        except Exception as e2:
            conn2.close()
            return {
                "success":        False,
                "sql":            fixed_sql,
                "rows":           [],
                "columns":        [],
                "attempts":       2,
                "fixed":          False,
                "error":          str(e2),
                "original_sql":   sql,
                "original_error": error_msg
            }
