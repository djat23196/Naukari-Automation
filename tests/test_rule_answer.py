"""Regression tests for rule_answer — locks in correct profile-based answers."""
import json
import pytest
from answer_engine import rule_answer


@pytest.fixture
def profile():
    with open("config.json") as f:
        return json.load(f)["profile"]


# ── CTC ──────────────────────────────────────────────────────────────────

class TestCTC:
    def test_current_ctc(self, profile):
        assert rule_answer("What is your current CTC?", profile) == "17 LPA"

    def test_current_salary(self, profile):
        assert rule_answer("What is your current salary?", profile) == "17 LPA"

    def test_present_ctc(self, profile):
        assert rule_answer("What is your present CTC?", profile) == "17 LPA"

    def test_expected_ctc(self, profile):
        assert rule_answer("What is your expected CTC?", profile) == "22 LPA"

    def test_desired_salary(self, profile):
        assert rule_answer("What is your desired salary?", profile) == "22 LPA"

    def test_expected_before_current(self, profile):
        """'expected' must not accidentally match 'current' rules."""
        assert rule_answer("What is your expected CTC?", profile) == "22 LPA"
        assert rule_answer("What is your current CTC?", profile) == "17 LPA"


# ── Notice Period ────────────────────────────────────────────────────────

class TestNoticePeriod:
    def test_notice_period(self, profile):
        assert rule_answer("What is your notice period?", profile) == "30 days"

    def test_notice_period_cased(self, profile):
        assert rule_answer("NOTICE PERIOD in days?", profile) == "30 days"


# ── Location ─────────────────────────────────────────────────────────────

class TestLocation:
    def test_current_location(self, profile):
        assert rule_answer("What is your current location?", profile) == "Bangalore"

    def test_current_city(self, profile):
        assert rule_answer("What is your current city?", profile) == "Bangalore"

    def test_preferred_location(self, profile):
        assert rule_answer("What is your preferred location?", profile) == "Bangalore"

    def test_where_based(self, profile):
        assert rule_answer("Where are you based?", profile) == "Bangalore"


# ── Company ──────────────────────────────────────────────────────────────

class TestCompany:
    def test_current_company(self, profile):
        assert rule_answer("What is your current company?", profile) == "Acies Global"

    def test_current_employer(self, profile):
        assert rule_answer("Who is your current employer?", profile) == "Acies Global"


# ── Qualification ────────────────────────────────────────────────────────

class TestQualification:
    def test_qualification(self, profile):
        assert rule_answer("What is your highest qualification?", profile) == "Bachelor of Engineering"

    def test_degree(self, profile):
        assert rule_answer("What is your degree?", profile) == "Bachelor of Engineering"


# ── Yes/No Questions ─────────────────────────────────────────────────────

class TestYesNo:
    @pytest.mark.parametrize("question", [
        "Are you willing to relocate?",
        "Are you open to night shifts?",
        "Can you work from office?",
        "Do you have experience in Python?",
        "Are you familiar with AWS?",
        "Have you worked on ML projects?",
        "Are you available for immediate joining?",
        "Are you residing in Bangalore?",
    ])
    def test_yes_questions(self, profile, question):
        assert rule_answer(question, profile) == "Yes"

    @pytest.mark.parametrize("question", [
        "Have you ever been employed with Google?",
        "Have you previously worked at Microsoft?",
        "Are you a former employee of TCS?",
    ])
    def test_no_questions(self, profile, question):
        assert rule_answer(question, profile) == "No"

    def test_negotiable(self, profile):
        assert rule_answer("Is your salary negotiable?", profile) == "Yes"


# ── Experience: Total ────────────────────────────────────────────────────

class TestTotalExperience:
    def test_total_experience(self, profile):
        assert rule_answer("What is your total experience?", profile) == "5.5"

    def test_overall_experience(self, profile):
        assert rule_answer("How many years of overall experience do you have?", profile) == "5.5"

    def test_total_work_experience(self, profile):
        assert rule_answer("What is your total work experience?", profile) == "5.5"


# ── Experience: Skill-Specific ───────────────────────────────────────────

class TestSkillExperience:
    @pytest.mark.parametrize("skill,expected", [
        ("python", "5"),
        ("machine learning", "5"),
        ("deep learning", "3"),
        ("nlp", "4"),
        ("pytorch", "2"),
        ("computer vision", "3"),
        ("langgraph", "1"),
        ("docker", "2"),
        ("databricks", "2"),
        ("tensorflow", "3"),
        ("generative ai", "2"),
        ("clickhouse", "1"),
    ])
    def test_known_skills(self, profile, skill, expected):
        question = f"How many years of experience do you have in {skill}?"
        assert rule_answer(question, profile) == expected

    def test_unknown_skill_returns_none(self, profile):
        """Unknown skills must NOT return total experience — let LLM handle it."""
        assert rule_answer("How many years of experience do you have in React?", profile) is None

    def test_unknown_skill_java(self, profile):
        assert rule_answer("How many years of experience do you have in Java?", profile) is None

    def test_unknown_skill_angular(self, profile):
        assert rule_answer("How many years of experience do you have in Angular?", profile) is None


# ── Unmatched Questions ──────────────────────────────────────────────────

class TestUnmatched:
    def test_random_text_returns_none(self, profile):
        assert rule_answer("Tell me about your hobbies", profile) is None

    def test_empty_question(self, profile):
        assert rule_answer("", profile) is None
