"""Dynamic chatbot answer engine: rules first, LLM fallback (Groq primary, OpenRouter secondary)."""
from __future__ import annotations

import os

import httpx


def validate_api_keys() -> tuple[bool, str]:
    """Check that at least one LLM API key is configured."""
    groq = os.getenv("GROQ_API_KEY", "")
    openrouter = os.getenv("OPENROUTER_API_KEY", "")
    if groq and openrouter:
        return True, "API keys: Groq + OpenRouter configured"
    if groq:
        return True, "API keys: Groq configured (no OpenRouter fallback)"
    if openrouter:
        return True, "API keys: OpenRouter configured (no Groq primary)"
    return False, "No LLM API keys found. Set GROQ_API_KEY or OPENROUTER_API_KEY in .env"


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


def _build_profile_block(profile: dict) -> str:
    """Build structured profile text for the LLM from the profile dict."""
    skills = profile.get("skills", {})
    skills_str = ", ".join(f"{k}: {v}yr" for k, v in skills.items()) if skills else "N/A"

    return (
        f"Total experience: {profile.get('total_experience', 'N/A')} years\n"
        f"Current CTC: {profile.get('current_ctc', 'N/A')}\n"
        f"Expected CTC: {profile.get('expected_ctc', 'N/A')}\n"
        f"Notice period: {profile.get('notice_period', 'N/A')}\n"
        f"Current location: {profile.get('current_location', 'N/A')}\n"
        f"Current company: {profile.get('current_company', 'N/A')}\n"
        f"Qualification: {profile.get('qualification', 'N/A')}\n"
        f"Native location: {profile.get('native_location', 'N/A')}\n"
        f"Skills (with years of experience): {skills_str}\n"
        f"Summary: {profile.get('resume_summary', '')}"
    )


_FEW_SHOT = (
    "\n\nExamples of expected answers:\n"
    'Q: "How many years of experience do you have in Python?" → A: "5"\n'
    'Q: "What is your current CTC?" → A: "12 LPA"\n'
    'Q: "Are you willing to relocate?" → A: "Yes"\n'
    'Q: "What is your notice period?" → A: "30 days"\n'
    'Q: "What is your highest qualification?" → A: "Bachelor of Engineering"\n'
)

_ANSWER_HINTS = (
    "\n\nAnswer format rules:\n"
    "- For 'how many years' questions: respond with a NUMBER ONLY (e.g. '3').\n"
    "- For CTC/salary questions: respond with number + LPA (e.g. '12 LPA').\n"
    "- For yes/no questions: respond with 'Yes' or 'No'.\n"
    "- For location questions: respond with city name only.\n"
    "- Never exceed 5 words. No explanations or sentences.\n"
    "- Use ONLY the data provided in the profile. Do NOT guess or invent numbers.\n"
)


def _build_system_prompt(profile: dict, available_options: list[str] | None) -> str:
    profile_block = _build_profile_block(profile)

    if available_options:
        return (
            "You are answering a recruiter's chatbot question for a job application.\n"
            f"You MUST pick EXACTLY one of these options: {available_options}.\n"
            "Return ONLY the exact option text, nothing else.\n\n"
            f"Candidate profile:\n{profile_block}"
            f"{_FEW_SHOT}"
        )
    return (
        "You are answering a recruiter's chatbot question for a job application.\n"
        "Answer in 1-5 words only. No explanations, no sentences. Just the answer.\n\n"
        f"Candidate profile:\n{profile_block}"
        f"{_FEW_SHOT}"
        f"{_ANSWER_HINTS}"
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
                "max_tokens": 50,
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
                    "max_tokens": 50,
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
    system_prompt = _build_system_prompt(profile, available_options)

    # Try Groq first (fast, reliable)
    answer = _call_groq(question, system_prompt, config)
    if answer:
        return answer

    # Fallback: OpenRouter
    answer = _call_openrouter(question, system_prompt, config)
    if answer:
        return answer

    return None
