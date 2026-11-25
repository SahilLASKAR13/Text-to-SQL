from core.clarification_engine import ClarificationEngine, ClarificationQuestion
from core.llm_handler import LLMError


class ScriptedLLM:
    """Returns queued JSON replies in order."""

    def __init__(self, *replies):
        self.replies = list(replies)

    def chat_json(self, system, user, **kwargs):
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


CLEAR = {"intent": "avg salary", "can_answer": True, "ambiguities": [], "confidence": 0.95,
         "assumptions": ["average means mean"]}

AMBIGUOUS = {
    "intent": "top customers", "can_answer": True, "confidence": 0.4,
    "ambiguities": [{"issue": "Rank by what", "options": ["Revenue", "Orders"]}],
}


def test_clear_question_skips_clarification():
    result = ClarificationEngine(ScriptedLLM(CLEAR)).analyze("average salary?", "schema")
    assert result.can_answer and not result.needs_clarification
    assert result.assumptions == ["average means mean"]


def test_ambiguous_question_asks_user():
    wording = {"questions": [{"question": "Rank customers by what?", "options": ["Revenue", "Orders"]}]}
    result = ClarificationEngine(ScriptedLLM(AMBIGUOUS, wording)).analyze("top customers", "schema")
    assert result.needs_clarification
    assert result.questions[0].options == ["Revenue", "Orders"]


def test_high_confidence_ignores_minor_ambiguity():
    data = {**AMBIGUOUS, "confidence": 0.9}
    result = ClarificationEngine(ScriptedLLM(data)).analyze("top customers", "schema")
    assert not result.needs_clarification


def test_unanswerable_question():
    data = {"can_answer": False, "cannot_answer_reason": "No revenue column", "confidence": 0.9}
    result = ClarificationEngine(ScriptedLLM(data)).analyze("total revenue", "schema")
    assert not result.can_answer
    assert result.reason == "No revenue column"


def test_falls_back_to_raw_ambiguities_when_wording_fails():
    result = ClarificationEngine(ScriptedLLM(AMBIGUOUS, LLMError("boom"))).analyze("top customers", "s")
    assert result.needs_clarification
    assert result.questions[0].question == "Rank by what?"


def test_analysis_failure_does_not_block_user():
    result = ClarificationEngine(ScriptedLLM(LLMError("down"))).analyze("anything", "schema")
    assert result.can_answer and not result.needs_clarification


def test_merge_answers_skips_blank_answers():
    qs = [ClarificationQuestion("Rank by?", ["A"]), ClarificationQuestion("Period?", ["B"])]
    notes = ClarificationEngine.merge_answers(qs, {0: "Revenue", 1: "  "})
    assert notes == "- Rank by? -> Revenue"
