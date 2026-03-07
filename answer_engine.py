"""Dynamic chatbot answer engine: rules first, LLM fallback (Groq primary, OpenRouter secondary)."""
from __future__ import annotations

import os

import httpx


def answer_question(
    question: str,
    config: dict,
    available_options: list[str] | None = None,
) -> str:
    """Answer a chatbot question using rules first, LLM fallback."""
    profile = config.get("profile", {})

    answer = rule_answer(question, profile)
    if answer:
        return answer

    answer = llm_answer(question, profile, config, available_options=available_options)
    if answer:
        return answer

    default = profile.get("default_experience", "3")
    print(f"    [chat] A (default): {default}")
    return default


def rule_answer(question: str, profile: dict) -> str | None:
    """Match question against known patterns and return answer from profile."""
    q = question.lower()

    # Quick yes/no checks FIRST (before salary, to catch "is your salary negotiable")
    if any(kw in q for kw in ["negotiable", "flexible"]):
        return "Yes"

    # Salary — check expected BEFORE current
    if any(kw in q for kw in ["expected ctc", "expected salary", "desired salary", "desired ctc",
                               "expected in-hand"]):
        return profile.get("expected_ctc", "")
    if any(kw in q for kw in ["current ctc", "current salary", "present ctc", "present salary",
                               "current in-hand", "in-hand per month"]):
        return profile.get("current_ctc", "")

    # Notice period
    if "notice period" in q:
        return profile.get("notice_period", "30 days")

    # Location — flexible, willing to relocate anywhere
    if any(kw in q for kw in ["current location", "current city", "where are you based",
                               "where do you live", "where do you stay"]):
        return profile.get("current_location", "")
    if any(kw in q for kw in ["preferred location", "preferred city", "select the city",
                               "select your city", "select location"]):
        return profile.get("current_location", "")

    # Company
    if any(kw in q for kw in ["current company", "current employer", "currently working", "current organization"]):
        return profile.get("current_company", "")

    # Qualification
    if any(kw in q for kw in ["qualification", "education", "degree", "highest degree"]):
        return profile.get("qualification", "")

    # Negative questions — answer "No"
    if any(kw in q for kw in ["have you ever been employed with", "have you previously worked at",
                               "are you a former employee"]):
        return "No"

    # Yes/No questions — answer "Yes"
    if any(kw in q for kw in ["willing to", "are you open", "can you", "do you agree", "ready to",
                               "comfortable with", "ok with", "okay with", "interested in",
                               "do you have experience", "do you have knowledge",
                               "are you familiar", "have you worked", "do you know",
                               "say yes", "confirm yes", "available in",
                               "residing in", "willing to relocate",
                               "are you available", "available for"]):
        return "Yes"

    # Experience/skill-in-years questions
    if any(kw in q for kw in ["years of experience", "experience do you have", "how many years",
                               "yrs of experience", "years experience",
                               "in years", "exposure with", "specify experience",
                               "specify knowledge", "knowledge of"]):
        skills = profile.get("skills", {})
        sorted_skills = sorted(skills.items(), key=lambda x: len(x[0]), reverse=True)
        for skill, years in sorted_skills:
            if skill.lower() in q:
                return str(years)
        return profile.get("total_experience", profile.get("default_experience", "3"))

    return None


def _build_system_prompt(resume: str, available_options: list[str] | None) -> str:
    if available_options:
        return (
            "You are answering a recruiter's chatbot question for a job application. "
            f"You MUST pick EXACTLY one of these options: {available_options}. "
            "Return ONLY the exact option text, nothing else. "
            f"Based on this candidate profile: {resume}"
        )
    return (
        "You are answering a recruiter's chatbot question for a job application. "
        "Answer in 1-5 words only. No explanations, no sentences. Just the answer. "
        f"Based on this candidate profile: {resume}"
    )


def _call_groq(question: str, system_prompt: str, config: dict) -> str | None:
    """Call Groq API (fast, reliable)."""
    api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key:
        return None

    model = config.get("groq_model", "llama-3.3-70b-versatile")
    try:
        resp = httpx.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": question},
                ],
                "max_tokens": 20,
                "temperature": 0.1,
            },
            timeout=10,
        )
        if resp.status_code == 200:
            answer = resp.json()["choices"][0]["message"]["content"].strip()
            if answer:
                print(f"    [chat] A (Groq): {answer}")
                return answer
        else:
            print(f"    [chat] Groq error: {resp.status_code}")
    except Exception as exc:
        print(f"    [chat] Groq exception: {exc}")
    return None


def _call_openrouter(question: str, system_prompt: str, config: dict) -> str | None:
    """Call OpenRouter API (fallback)."""
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    if not api_key:
        return None

    models = config.get("openrouter_models", [])
    for model in models:
        try:
            resp = httpx.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": question},
                    ],
                    "max_tokens": 20,
                    "temperature": 0.1,
                },
                timeout=10,
            )
            if resp.status_code == 200:
                answer = resp.json()["choices"][0]["message"]["content"].strip()
                if answer:
                    print(f"    [chat] A (LLM {model.split('/')[0]}): {answer}")
                    return answer
        except Exception:
            continue
    return None


def llm_answer(
    question: str,
    profile: dict,
    config: dict,
    available_options: list[str] | None = None,
) -> str | None:
    """Call LLM to answer questions. Tries Groq first, then OpenRouter."""
    resume = profile.get("resume_summary", "")
    system_prompt = _build_system_prompt(resume, available_options)

    # Try Groq first (fast, reliable)
    answer = _call_groq(question, system_prompt, config)
    if answer:
        return answer

    # Fallback: OpenRouter
    answer = _call_openrouter(question, system_prompt, config)
    if answer:
        return answer

    return None
