"""Step 2 of the clarification engine: turn ambiguities into friendly questions."""
from __future__ import annotations

import json

SYSTEM_PROMPT = """You write short clarifying questions for non-technical business users who are querying their own data.
You are given the user's question and a list of ambiguities. Write one question per ambiguity.

Return ONLY a JSON object with exactly this shape:
{"questions": [{"question": "<clear question>", "options": ["<choice>", "<choice>"]}]}

Rules:
- Plain, friendly language. No SQL terms. Mention column names only when it helps the user choose.
- 2 to 4 options per question: concrete, mutually exclusive, short.
- Do not add an "Other" option; the interface already lets the user type their own answer.
- Never ask more questions than there are ambiguities (maximum 3).
"""


def build_user_prompt(question: str, ambiguities: list[dict], schema_text: str) -> str:
    return (
        f"DATABASE SCHEMA:\n{schema_text}\n\n"
        f"USER QUESTION: {question}\n\n"
        f"AMBIGUITIES:\n{json.dumps(ambiguities, indent=2)}\n\n"
        "Respond with the JSON object only."
    )
