"""In-memory SQLite database that holds the user's uploaded tables."""
from __future__ import annotations

import sqlite3

import pandas as pd


class DatabaseManager:
    def __init__(self) -> None:
        # check_same_thread=False: Streamlit may run reruns on different threads
        self.conn = sqlite3.connect(":memory:", check_same_thread=False)
        self.table_names: list[str] = []

    def load_tables(self, tables: dict[str, pd.DataFrame]) -> None:
        self.conn.execute("PRAGMA query_only = OFF")
        self.table_names = []
        for name, df in tables.items():
            df.to_sql(name, self.conn, if_exists="replace", index=False)
            self.table_names.append(name)
        self.conn.commit()
        # From here on the connection physically cannot write: a second safety net
        # behind the SQL validator.
        self.conn.execute("PRAGMA query_only = ON")

    def get_columns(self, table: str) -> list[str]:
        rows = self.conn.execute(f'PRAGMA table_info("{table}")').fetchall()
        return [r[1] for r in rows]

    def close(self) -> None:
        self.conn.close()
