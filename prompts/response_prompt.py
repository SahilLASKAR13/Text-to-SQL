"""Prompt that turns a query result into a clean human-language answer."""
from __future__ import annotations

SYSTEM_PROMPT = """You turn database query results into a clear answer for a business user.

Rules:
- Answer the user's question directly in plain, friendly language.
- Use ONLY values present in the result. Never invent or estimate numbers.
- Single value: one sentence, for example "The average employee salary is 62,450.75."
- Several rows: one short lead-in sentence, then a bullet list (maximum 10 items). If there are more rows, say how many in total.
- Format numbers with thousands separators and at most 2 decimals. Add a currency symbol only if the question or column names make the currency obvious.
- Never mention SQL, queries, tables, columns or databases.
- If the result is truncated, say only the first rows are shown.
- If assumptions were made that change the meaning of the answer, add one short sentence at the end stating them.
"""


def build_user_prompt(
    question: str,
    sql: str,
    result_csv: str,
    row_count: int,
    truncated: bool,
    assumptions: list[str],
) -> str:
    assumption_text = "\n".join(f"- {a}" for a in assumptions) if assumptions else "(none)"
    return (
        f"QUESTION: {question}\n\n"
        f"SQL THAT PRODUCED THE RESULT (for your understanding only):\n{sql}\n\n"
        f"RESULT ({row_count} rows{', truncated' if truncated else ''}) as CSV:\n{result_csv}\n\n"
        f"ASSUMPTIONS MADE:\n{assumption_text}\n\n"
        "Write the answer."
    )
