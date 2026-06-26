import sqlite3


class SchemaLinker:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def extract_schema(self) -> dict:
        """Reads any SQLite database and extracts full schema automatically."""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cur.fetchall()]

        schema = {}
        for table in tables:
            cur.execute(f"PRAGMA table_info({table})")
            cols = [(row[1], row[2]) for row in cur.fetchall()]

            cur.execute(f"SELECT * FROM {table} LIMIT 3")
            samples = cur.fetchall()

            cur.execute(f"SELECT COUNT(*) FROM {table}")
            count = cur.fetchone()[0]

            schema[table] = {
                "columns":   cols,
                "samples":   samples,
                "row_count": count
            }

        conn.close()
        return schema

    def to_prompt_string(self) -> str:
        """Converts schema into a rich string for the LLM prompt."""
        schema = self.extract_schema()
        lines = []
        for table, info in schema.items():
            col_str = ", ".join(f"{c[0]}({c[1]})" for c in info["columns"])
            lines.append(f"Table '{table}' ({info['row_count']} rows): {col_str}")
            if info["samples"]:
                lines.append(f"  Sample row: {info['samples'][0]}")
        return "\n".join(lines)

    def to_simple_string(self) -> str:
        """Simple schema string for UI display."""
        schema = self.extract_schema()
        lines = []
        for table, info in schema.items():
            col_str = ", ".join(c[0] for c in info["columns"])
            lines.append(f"{table}({col_str})")
        return "\n".join(lines)
