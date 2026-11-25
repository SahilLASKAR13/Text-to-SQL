"""Decides whether a question is clear enough, and if not, what to ask the user."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from config.settings import settings
from core.llm_handler import LLMError
from prompts import clarification_prompt, understanding_prompt

logger = logging.getLogger(__name__)


@dataclass
class ClarificationQuestion:
    question: str
    options: list[str] = field(default_factory=list)


@dataclass
class ClarificationResult:
    can_answer: bool = True
    reason: str = ""
    needs_clarification: bool = False
    questions: list[ClarificationQuestion] = field(default_factory=list)
    understanding: dict = field(default_factory=dict)

    @property
    def assumptions(self) -> list[str]:
        return list(self.understanding.get("assumptions", []))


class ClarificationEngine:
    def __init__(
        self,
        llm,
        threshold: float | None = None,
        max_questions: int | None = None,
    ) -> None:
        self.llm = llm
        self.threshold = settings.clarification_threshold if threshold is None else threshold
        self.max_questions = max_questions or settings.max_clarification_questions

    # ------------------------------------------------------------------ public
    def analyze(
        self, question: str, schema_text: str, history: list[dict] | None = None
    ) -> ClarificationResult:
        try:
            raw = self.llm.chat_json(
                understanding_prompt.SYSTEM_PROMPT,
                understanding_prompt.build_user_prompt(question, schema_text, history),
            )
        except (LLMError, ValueError) as exc:
            # Never block the user because the analysis step failed: just try to answer.
            logger.warning("Understanding step failed, skipping clarification: %s", exc)
            return ClarificationResult()

        understanding = self._normalize(raw)
        if not understanding["can_answer"]:
            return ClarificationResult(
                can_answer=False,
                reason=understanding["cannot_answer_reason"]
                or "The uploaded data doesn't seem to contain what's needed to answer that.",
                understanding=understanding,
            )

        ambiguities = understanding["ambiguities"]
        needs = bool(ambiguities) and understanding["confidence"] < self.threshold
        questions = self._build_questions(question, schema_text, ambiguities) if needs else []
        return ClarificationResult(
            needs_clarification=bool(questions),
            questions=questions,
            understanding=understanding,
        )

    @staticmethod
    def merge_answers(questions: list[ClarificationQuestion], answers: dict[int, str]) -> str:
        """Turn the user's answers into a note for the SQL generator."""
        lines = [
            f"- {q.question} -> {answers[i].strip()}"
            for i, q in enumerate(questions)
            if answers.get(i, "").strip()
        ]
        return "\n".join(lines)

    # ----------------------------------------------------------------- helpers
    def _normalize(self, raw: dict) -> dict:
        try:
            confidence = float(raw.get("confidence", 1.0))
        except (TypeError, ValueError):
            confidence = 1.0
        ambiguities = [
            a
            for a in raw.get("ambiguities", []) or []
            if isinstance(a, dict) and a.get("issue")
        ][: self.max_questions]
        return {
            "intent": str(raw.get("intent", "")),
            "can_answer": bool(raw.get("can_answer", True)),
            "cannot_answer_reason": str(raw.get("cannot_answer_reason", "") or ""),
            "relevant_tables": raw.get("relevant_tables", []) or [],
            "relevant_columns": raw.get("relevant_columns", []) or [],
            "assumptions": [str(a) for a in (raw.get("assumptions", []) or [])],
            "ambiguities": ambiguities,
            "confidence": max(0.0, min(1.0, confidence)),
        }

    def _build_questions(
        self, question: str, schema_text: str, ambiguities: list[dict]
    ) -> list[ClarificationQuestion]:
        try:
            raw = self.llm.chat_json(
                clarification_prompt.SYSTEM_PROMPT,
                clarification_prompt.build_user_prompt(question, ambiguities, schema_text),
                temperature=0.2,
            )
            questions = []
            for item in raw.get("questions", []):
                text = str(item.get("question", "")).strip()
                options = [str(o).strip() for o in item.get("options", []) if str(o).strip()]
                if text:
                    questions.append(ClarificationQuestion(text, options[:4]))
            if questions:
                return questions[: self.max_questions]
        except (LLMError, ValueError, AttributeError) as exc:
            logger.warning("Clarification wording failed, using raw ambiguities: %s", exc)

        # Fallback: use the ambiguities exactly as the analysis produced them
        return [
            ClarificationQuestion(
                question=f"{a['issue'].rstrip('?')}?",
                options=[str(o) for o in a.get("options", [])][:4],
            )
            for a in ambiguities
        ]
