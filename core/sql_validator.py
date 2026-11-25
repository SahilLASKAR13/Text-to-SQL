"""Makes sure generated SQL is a single, read-only, valid SQLite SELECT."""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass

_STRING_LITERAL = re.compile(r"'(?:[^']|'')*'")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT = re.compile(r"--[^\n]*")

_FORBIDDEN = (
    "insert", "update", "delete", "drop", "alter", "create", "truncate", "attach",
    "detach", "pragma", "vacuum", "reindex", "grant", "revoke", "load_extension",
)
_FORBIDDEN_RE = re.compile(r"\b(" + "|".join(_FORBIDDEN) + r")\b", re.IGNORECASE)


@dataclass
class ValidationResult:
    is_valid: bool
    sql: str
    error: str | None = None


class SQLValidator:
    def __init__(self, db) -> None:
        self.db = db

    def validate(self, sql: str) -> ValidationResult:
        sql = (sql or "").strip().rstrip(";").strip()
        if not sql:
            return ValidationResult(False, sql, "The generated query was empty.")

        # Analyse a copy with string literals and comments removed
        probe = _STRING_LITERAL.sub("''", sql)
        probe = _BLOCK_COMMENT.sub(" ", probe)
        probe = _LINE_COMMENT.sub(" ", probe).strip()

        if ";" in probe:
            return ValidationResult(False, sql, "Only a single SQL statement is allowed.")
        if not re.match(r"^(select|with)\b", probe, flags=re.IGNORECASE):
            return ValidationResult(False, sql, "Only SELECT queries are allowed.")
        forbidden = _FORBIDDEN_RE.search(probe)
        if forbidden:
            return ValidationResult(
                False, sql, f"The keyword '{forbidden.group(1).upper()}' is not allowed (read-only)."
            )

        # Let SQLite itself check tables, columns and syntax without running the query
        try:
            self.db.conn.execute(f"EXPLAIN {sql}").fetchall()
        except sqlite3.Error as exc:
            return ValidationResult(False, sql, str(exc))

        return ValidationResult(True, sql)
