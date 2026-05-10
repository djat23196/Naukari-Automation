"""Regression tests for answer_question and decide_answer contracts."""
import json
import pytest
from answer_engine import answer_question
from chatbot import decide_answer


@pytest.fixture
def config():
    with open("config.json") as f:
        return json.load(f)


# ── answer_question Return Type ──────────────────────────────────────────

class TestAnswerQuestionContract:
    def test_returns_tuple(self, config):
        result = answer_question("What is your CTC?", config)
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_returns_str_str(self, config):
        ans, src = answer_question("What is your current CTC?", config)
        assert isinstance(ans, str)
        assert isinstance(src, str)

    def test_rule_source(self, config):
        _, src = answer_question("What is your current CTC?", config)
        assert src == "rule"

    def test_ctc_value(self, config):
        ans, _ = answer_question("What is your expected CTC?", config)
        assert ans == "22 LPA"


# ── decide_answer Return Type ────────────────────────────────────────────

class TestDecideAnswerContract:
    def _snapshot(self, question, options=None, text_input=None, has_skip=False):
        return {
            "question": question,
            "options": options or [],
            "text_input": text_input,
            "has_save": True,
            "has_skip": has_skip,
        }

    def test_returns_3_tuple(self, config):
        snap = self._snapshot("What is your notice period?", options=[
            {"text": "15 days", "type": "radio", "value": "15"},
            {"text": "1 month", "type": "radio", "value": "30"},
        ])
        result = decide_answer(snap, config)
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_config_source_for_notice(self, config):
        snap = self._snapshot("What is your notice period?", options=[
            {"text": "15 days", "type": "radio", "value": "15"},
            {"text": "1 month", "type": "radio", "value": "30"},
        ])
        ans, method, source = decide_answer(snap, config)
        assert ans == "1 month"
        assert method == "click_radio"
        assert source == "config"

    def test_rule_source_for_relocation(self, config):
        snap = self._snapshot("Are you willing to relocate?", options=[
            {"text": "Yes", "type": "radio", "value": "yes"},
            {"text": "No", "type": "radio", "value": "no"},
        ])
        ans, method, source = decide_answer(snap, config)
        assert ans == "Yes"
        assert source in ("config", "rule")

    def test_text_input_returns_source(self, config):
        snap = self._snapshot(
            "What is your expected CTC?",
            text_input={"placeholder": "", "id": ""},
        )
        ans, method, source = decide_answer(snap, config)
        assert method == "text"
        assert ans == "22 LPA"
        assert source == "rule"

    def test_skip_when_no_match(self, config):
        snap = self._snapshot(
            "Some very specific company question?",
            options=[{"text": "Option X", "type": "radio", "value": "x"}],
            has_skip=True,
        )
        ans, method, source = decide_answer(snap, config)
        assert source in ("skip", "llm_groq", "llm_openrouter", "config", "rule")

    def test_no_answer_returns_none(self, config):
        snap = self._snapshot("")
        ans, method, source = decide_answer(snap, config)
        assert ans is None
        assert method is None
        assert source == "none"

    def test_metadata_rejected(self, config):
        snap = self._snapshot("Thank you for applying! 3 days ago")
        ans, method, source = decide_answer(snap, config)
        assert ans is None
        assert source == "none"
