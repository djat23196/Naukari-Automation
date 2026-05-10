"""Regression tests for chatbot_logger — JSONL output format and correctness."""
import json
import os
import shutil
import pytest
from chatbot_logger import log_interaction, LOG_DIR, LOG_FILE


@pytest.fixture(autouse=True)
def clean_logs():
    """Remove logs dir before and after each test."""
    if os.path.exists(LOG_DIR):
        shutil.rmtree(LOG_DIR)
    yield
    if os.path.exists(LOG_DIR):
        shutil.rmtree(LOG_DIR)


class TestLogInteraction:
    def test_creates_directory(self):
        assert not os.path.exists(LOG_DIR)
        log_interaction(
            question="test?", answer="yes", source="rule",
            method="text", success=True,
        )
        assert os.path.isdir(LOG_DIR)

    def test_creates_file(self):
        log_interaction(
            question="test?", answer="yes", source="rule",
            method="text", success=True,
        )
        assert os.path.isfile(LOG_FILE)

    def test_valid_json_line(self):
        log_interaction(
            question="What is your CTC?", answer="17 LPA",
            source="rule", method="text", success=True,
        )
        with open(LOG_FILE) as f:
            line = f.readline()
        record = json.loads(line)
        assert isinstance(record, dict)

    def test_all_fields_present(self):
        log_interaction(
            job_title="ML Engineer", company="TestCorp",
            question="CTC?", options=["10", "20"],
            answer="20", source="config", method="click_radio",
            success=True, round_num=3,
        )
        with open(LOG_FILE) as f:
            record = json.loads(f.readline())

        expected_keys = {
            "timestamp", "job_title", "company", "question",
            "options", "answer", "source", "method", "success", "round",
        }
        assert set(record.keys()) == expected_keys

    def test_field_values(self):
        log_interaction(
            job_title="AI Engineer", company="BigCo",
            question="Notice period?", options=None,
            answer="30 days", source="rule", method="text",
            success=True, round_num=1,
        )
        with open(LOG_FILE) as f:
            record = json.loads(f.readline())

        assert record["job_title"] == "AI Engineer"
        assert record["company"] == "BigCo"
        assert record["question"] == "Notice period?"
        assert record["options"] is None
        assert record["answer"] == "30 days"
        assert record["source"] == "rule"
        assert record["method"] == "text"
        assert record["success"] is True
        assert record["round"] == 1

    def test_failure_record(self):
        log_interaction(
            question="Unknown?", answer=None,
            source="none", method=None, success=False,
        )
        with open(LOG_FILE) as f:
            record = json.loads(f.readline())

        assert record["answer"] is None
        assert record["method"] is None
        assert record["success"] is False

    def test_append_multiple(self):
        for i in range(5):
            log_interaction(
                question=f"Q{i}?", answer=str(i),
                source="rule", method="text", success=True,
            )
        with open(LOG_FILE) as f:
            lines = f.readlines()
        assert len(lines) == 5
        for i, line in enumerate(lines):
            record = json.loads(line)
            assert record["question"] == f"Q{i}?"

    def test_unicode_handling(self):
        log_interaction(
            job_title="ÄI Engineer — Zürich",
            company="Tëst Cörp",
            question="Können Sie Deutsch?",
            answer="Ja", source="rule", method="text", success=True,
        )
        with open(LOG_FILE, encoding="utf-8") as f:
            record = json.loads(f.readline())
        assert record["job_title"] == "ÄI Engineer — Zürich"

    def test_timestamp_format(self):
        log_interaction(
            question="test?", answer="yes",
            source="rule", method="text", success=True,
        )
        with open(LOG_FILE) as f:
            record = json.loads(f.readline())
        ts = record["timestamp"]
        assert "T" in ts
        assert "+" in ts or "-" in ts
