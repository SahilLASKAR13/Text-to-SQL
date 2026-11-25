"""Thin wrapper around the Groq chat API with retries and JSON helpers."""
from __future__ import annotations

import time

from utils.helpers import extract_json


class LLMError(Exception):
    """Raised when the LLM cannot be reached or returns unusable output."""


class LLMHandler:
    def __init__(self, api_key: str, model: str, max_retries: int = 3) -> None:
        if not api_key:
            raise LLMError("GROQ_API_KEY is missing. Add it to your .env file.")
        from groq import Groq  # imported lazily so tests can run without the package

        self.client = Groq(api_key=api_key)
        self.model = model
        self.max_retries = max_retries

    def chat(
        self,
        system: str,
        user: str,
        *,
        temperature: float = 0.0,
        max_tokens: int = 1024,
        json_mode: bool = False,
    ) -> str:
        kwargs = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                response = self.client.chat.completions.create(**kwargs)
                return response.choices[0].message.content or ""
            except Exception as exc:  # network, rate-limit, auth ...
                last_error = exc
                time.sleep(0.5 * (2**attempt))
        raise LLMError(f"LLM request failed: {last_error}") from last_error

    def chat_json(self, system: str, user: str, **kwargs) -> dict:
        text = self.chat(system, user, json_mode=True, **kwargs)
        try:
            return extract_json(text)
        except ValueError as exc:
            raise LLMError(f"LLM returned invalid JSON: {exc}") from exc
