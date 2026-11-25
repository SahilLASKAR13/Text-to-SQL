"""Turns a query result into a clear, human-language answer."""
from __future__ import annotations

import logging

import pandas as pd

from core.llm_handler import LLMError
from core.query_executor import QueryResult
from prompts import response_prompt
from utils.helpers import df_to_csv_snippet

logger = logging.getLogger(__name__)


def _fmt(value) -> str:
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, float):
        return f"{value:,.2f}"
    return str(value)


def fallback_answer(df: pd.DataFrame) -> str:
    """Used only if the LLM is unavailable."""
    if df.shape == (1, 1):
        return f"The result is **{_fmt(df.iat[0, 0])}**."
    return f"I found {len(df):,} matching rows. They are shown in the table below."


class ResponseGenerator:
    def __init__(self, llm) -> None:
        self.llm = llm

    def generate(
        self, question: str, result: QueryResult, assumptions: list[str] | None = None
    ) -> str:
        if result.df.empty:
            return "I ran the analysis but found no records matching your question."
        # A single NULL (for example AVG over no rows) is not a real answer
        if result.df.shape == (1, 1) and pd.isna(result.df.iat[0, 0]):
            return "There is no data available to answer that (the result is empty)."

        prompt = response_prompt.build_user_prompt(
            question=question,
            sql=result.sql,
            result_csv=df_to_csv_snippet(result.df),
            row_count=result.row_count,
            truncated=result.truncated,
            assumptions=assumptions or [],
        )
        try:
            return self.llm.chat(response_prompt.SYSTEM_PROMPT, prompt, temperature=0.2).strip()
        except LLMError as exc:
            logger.warning("Response generation failed, using fallback: %s", exc)
            return fallback_answer(result.df)
