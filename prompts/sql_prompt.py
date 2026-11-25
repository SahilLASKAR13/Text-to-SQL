"""Prompts for SQL generation and self-repair (SQLite dialect)."""
from __future__ import annotations

SYSTEM_PROMPT = """You are an expert SQLite analyst. Convert the user's question into ONE read-only SQLite query.

Hard rules:
- Output ONLY the SQL. No explanation, no markdown, no code fences.
- Exactly one statement, starting with SELECT or WITH. Never modify data or schema.
- Use ONLY the tables and columns in the schema, spelled exactly as given.
- Text comparisons must be case-insensitive: use LOWER(col) = LOWER('value') or LIKE.
- Dates are TEXT in YYYY-MM-DD form: use date(), strftime(), or direct comparison.
- Avoid integer division: CAST(x AS REAL) when computing ratios or percentages.
- Round computed decimals with ROUND(value, 2).
- SQLite has NO MEDIAN, STDDEV, VARIANCE or PERCENTILE functions. Compute a median with
  ORDER BY ... LIMIT 1 OFFSET (SELECT (COUNT(*) - 1) / 2 ...). Compute variance from AVG(x*x) - AVG(x)*AVG(x).
- Ignore NULLs sensibly (aggregates already do; filter explicitly when ranking).
- Give result columns short readable aliases (for example avg_salary, employee_count).
- For queries that list individual rows, add LIMIT 100 unless the user asked for everything.
- When the user clarified something, follow their clarification exactly.
"""


def _history_block(history: list[dict] | None) -> str:
    if not history:
        return "(none)"
    return "\n\n".join(
        f"Q: {h['question']}\nSQL: {h.get('sql', '')}\nA: {h.get('answer', '')[:200]}"
        for h in history
    )


def build_user_prompt(
    question: str,
    schema_text: str,
    history: list[dict] | None,
    clarifications: str,
    assumptions: list[str],
) -> str:
    parts = [
        f"DATABASE SCHEMA:\n{schema_text}",
        f"CONVERSATION SO FAR:\n{_history_block(history)}",
    ]
    if clarifications:
        parts.append(f"USER CLARIFICATIONS:\n{clarifications}")
    if assumptions:
        parts.append("ASSUMPTIONS TO APPLY:\n" + "\n".join(f"- {a}" for a in assumptions))
    parts.append(f"QUESTION: {question}\n\nSQL:")
    return "\n\n".join(parts)


def build_repair_prompt(
    question: str, schema_text: str, bad_sql: str, error: str, clarifications: str
) -> str:
    extra = f"USER CLARIFICATIONS:\n{clarifications}\n\n" if clarifications else ""
    return (
        f"DATABASE SCHEMA:\n{schema_text}\n\n{extra}"
        f"QUESTION: {question}\n\n"
        f"The following SQL failed.\nSQL:\n{bad_sql}\n\nERROR:\n{error}\n\n"
        "Write a corrected SQLite query that answers the question. Output ONLY the SQL."
    )
