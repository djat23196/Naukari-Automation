"""Structured logging for chatbot Q&A interactions — append-only JSONL."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone, timedelta

LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "chatbot_interactions.jsonl")
IST = timezone(timedelta(hours=5, minutes=30))


def log_interaction(
    *,
    job_title: str = "",
    company: str = "",
    question: str,
    options: list[str] | None = None,
    answer: str | None,
    source: str,
    method: str | None,
    success: bool,
    round_num: int = 0,
) -> None:
    """Append one interaction record to the JSONL log file."""
    os.makedirs(LOG_DIR, exist_ok=True)

    record = {
        "timestamp": datetime.now(IST).isoformat(),
        "job_title": job_title,
        "company": company,
        "question": question,
        "options": options,
        "answer": answer,
        "source": source,
        "method": method,
        "success": success,
        "round": round_num,
    }

    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
