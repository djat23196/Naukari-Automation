# Naukri Auto-Apply Bot

A Playwright-based Python bot that automates job applications on [Naukri.com](https://www.naukri.com). It logs into your account, searches for jobs matching your filters, and applies automatically — including answering application questions using an AI-powered answer engine.

## Features

- **Automated Login** — Human-like typing delays and popup dismissal
- **Configurable Search** — Keywords, location, experience range, freshness, company blacklist
- **Smart Apply** — Handles apply modals, chatbot questions, and multi-step forms
- **AI Answer Engine** — Uses LLMs (Groq / OpenRouter) to answer free-text application questions based on your profile
- **Title Filtering** — Only applies to jobs matching your target role keywords
- **Tracking** — Logs applied and externally-linked jobs to CSV files

## Tech Stack

- Python 3.12 (managed with [uv](https://docs.astral.sh/uv/))
- [Playwright](https://playwright.dev/python/) (sync API) for browser automation
- [python-dotenv](https://pypi.org/project/python-dotenv/) for credentials
- [httpx](https://www.python-httpx.org/) for LLM API calls
- [openpyxl](https://openpyxl.readthedocs.io/) for Excel tracking

## Project Structure

```
├── main.py            # Entry point — login → search → apply loop
├── login.py           # Naukri login with human-like delays
├── search.py          # Builds search URLs, extracts job listings
├── apply.py           # Applies to jobs, handles modals, tracks results
├── chatbot.py         # Handles chatbot-style application questions
├── answer_engine.py   # AI-powered answers using Groq/OpenRouter LLMs
├── config.json        # Search filters, profile, and LLM settings
├── .env               # Credentials (not committed)
└── .env.example       # Template for .env
```

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/djat23196/Naukari-Automation.git
cd Naukari-Automation
```

### 2. Install dependencies

```bash
uv sync
uv run playwright install chromium
```

### 3. Configure credentials

```bash
cp .env.example .env
```

Edit `.env` with your Naukri credentials and API keys:

```
NAUKRI_EMAIL=your_email@example.com
NAUKRI_PASSWORD=your_password_here
OPENROUTER_API_KEY=sk-or-v1-your_key_here
GROQ_API_KEY=gsk_your_groq_key_here
```

### 4. Configure search filters

Edit `config.json` to set your keywords, location, experience range, skills, profile summary, and other preferences.

## Usage

```bash
# Run with browser visible
uv run python main.py

# Run headless
uv run python main.py --headless

# Debug with Playwright Inspector
PWDEBUG=1 uv run python main.py
```

## Output

- `applied_jobs.csv` — Jobs successfully applied to
- `external_apply_jobs.csv` — Jobs that redirect to external sites

## Disclaimer

This tool is for **personal/educational use only**. Use responsibly and respect Naukri.com's Terms of Service. The authors are not responsible for any account restrictions resulting from automated usage.
