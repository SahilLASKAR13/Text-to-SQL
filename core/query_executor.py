"""Runs validated SQL against the in-memory database with limits."""
from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass

import pandas as pd

from config.settings import settings


class QueryExecutionError(Exception):
    """Raised when a query fails or exceeds the time limit."""


@dataclass
class QueryResult:
    df: pd.DataFrame
    sql: str
    truncated: bool = False

    @property
    def row_count(self) -> int:
        return len(self.df)


class QueryExecutor:
    def __init__(self, db, max_rows: int | None = None, timeout: float | None = None) -> None:
        self.db = db
        self.max_rows = max_rows or settings.max_result_rows
        self.timeout = timeout or settings.query_timeout_seconds

    def execute(self, sql: str) -> QueryResult:
        conn = self.db.conn
        start = time.monotonic()
        # Abort runaway queries (for example accidental cross joins)
        conn.set_progress_handler(lambda: 1 if time.monotonic() - start > self.timeout else 0, 10000)
        try:
            cursor = conn.execute(sql)
            columns = [d[0] for d in cursor.description or []]
            rows = cursor.fetchmany(self.max_rows + 1)
        except sqlite3.Error as exc:
            if "interrupted" in str(exc).lower():
                raise QueryExecutionError(
                    f"The query took longer than {self.timeout:.0f} seconds and was stopped."
                ) from exc
            raise QueryExecutionError(str(exc)) from exc
        finally:
            conn.set_progress_handler(None, 0)

        truncated = len(rows) > self.max_rows
        df = pd.DataFrame(rows[: self.max_rows], columns=columns)
        return QueryResult(df=df, sql=sql, truncated=truncated)
