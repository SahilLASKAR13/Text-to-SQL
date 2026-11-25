"""Generates (and repairs) SQL using the LLM."""
from __future__ import annotations

import re

from prompts import sql_prompt


def clean_sql(text: str) -> str:
    """Strip markdown fences / chatter so only the SQL statement remains."""
    text = text.strip()
    fenced = re.search(r"```(?:sql)?\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()
    match = re.search(r"\b(select|with)\b", text, flags=re.IGNORECASE)
    if match and match.start() > 0:
        text = text[match.start():]
    return text.strip().rstrip(";").strip()


class SQLGenerator:
    def __init__(self, llm) -> None:
        self.llm = llm

    def generate(
        self,
        question: str,
        schema_text: str,
        history: list[dict] | None = None,
        clarifications: str = "",
        assumptions: list[str] | None = None,
    ) -> str:
        prompt = sql_prompt.build_user_prompt(
            question, schema_text, history, clarifications, assumptions or []
        )
        return clean_sql(self.llm.chat(sql_prompt.SYSTEM_PROMPT, prompt, temperature=0.0))

    def repair(
        self,
        question: str,
        schema_text: str,
        bad_sql: str,
        error: str,
        clarifications: str = "",
    ) -> str:
        prompt = sql_prompt.build_repair_prompt(question, schema_text, bad_sql, error, clarifications)
        return clean_sql(self.llm.chat(sql_prompt.SYSTEM_PROMPT, prompt, temperature=0.0))
