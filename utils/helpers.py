"""Small, dependency-light helpers shared across modules."""
from __future__ import annotations

import json
import re

import pandas as pd

_SQL_RESERVED = {
    "select", "from", "where", "group", "order", "by", "limit", "table", "index", "key",
    "values", "default", "check", "references", "primary", "unique", "join", "left", "right",
    "inner", "outer", "on", "as", "and", "or", "not", "null", "case", "when", "then", "else",
    "end", "in", "is", "like", "between", "exists", "union", "all", "distinct", "having",
    "offset", "desc", "asc", "with", "transaction", "column", "add", "alter", "drop",
    "create", "insert", "update", "delete", "set", "into", "view", "trigger", "if", "for",
    "to", "of", "natural", "cross", "full", "match", "plan", "query", "rename", "replace",
    "rollback", "row", "rows", "window",
}


def to_snake_case(name: str, prefix: str = "col", suffix: str = "_col") -> str:
    """Turn any header into a safe, unquoted SQL identifier."""
    text = str(name).strip()
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", text)
    text = re.sub(r"[^0-9a-zA-Z]+", "_", text).strip("_").lower()
    if not text:
        text = prefix
    if text[0].isdigit():
        text = f"{prefix}_{text}"
    if text in _SQL_RESERVED:
        text = f"{text}{suffix}"
    return text


def make_unique(names: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    out: list[str] = []
    for n in names:
        if n in seen:
            seen[n] += 1
            out.append(f"{n}_{seen[n]}")
        else:
            seen[n] = 0
            out.append(n)
    return out


def extract_json(text: str) -> dict:
    """Parse a JSON object from LLM output, tolerating code fences and chatter."""
    cleaned = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start != -1 and end > start:
        return json.loads(cleaned[start : end + 1])
    raise ValueError("No JSON object found in LLM output")


def df_to_csv_snippet(df: pd.DataFrame, max_rows: int = 30) -> str:
    return df.head(max_rows).to_csv(index=False)


def escape_markdown_dollars(text: str) -> str:
    """Streamlit treats $...$ as LaTeX; escape so currency renders normally."""
    return text.replace("$", "\\$")
