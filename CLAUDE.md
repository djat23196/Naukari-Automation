# Naukri Auto-Apply Bot

## Overview
Playwright-based Python bot that automates job applications on Naukri.com.

## Project Structure
- `main.py` — Entry point, orchestrates login → search → apply loop
- `login.py` — Naukri login with human-like delays and popup dismissal
- `search.py` — Builds search URLs, extracts job listings from results
- `apply.py` — Applies to jobs, handles modals, tracks results in `applied_jobs.csv`
- `config.json` — Search filters (keywords, location, experience, freshness)

## Tech Stack
- Python 3.12 (managed with `uv`)
- Playwright (sync API) for browser automation
- python-dotenv for credentials

## Commands
- Run: `uv run python main.py`
- Run headless: `uv run python main.py --headless`
- Debug with Playwright Inspector: `PWDEBUG=1 uv run python main.py`
- Install deps: `uv sync`
- Install browsers: `uv run playwright install chromium`

## Safety & Anti-Detection
- Rotate sessions across days to avoid account flags
- Human-like typing delays (50-150ms per character) in login
- Random delays between actions (1-3s default)
- Respect Naukri's ToS — personal/learning use only

## Configuration
- `.env` — `NAUKRI_EMAIL` and `NAUKRI_PASSWORD` (never commit)
- `config.json` — Search parameters (keywords, location, experience range, freshness, max_pages)


## Workflow Orchestration

### 1. Plan Mode Default
- Enter plan mode for ANY non-trivial task (3+ steps or architectural decisions).
- If something goes sideways, STOP and re-plan immediately—don't keep pushing.
- Use plan mode for verification steps, not just building.
- Write detailed specs upfront to reduce ambiguity.

### 2. Subagent Strategy
- Use subagents liberally to keep main context window clean.
- Offload research, exploration, and parallel analysis to subagents.
- For complex problems, throw more compute at it via subagents.
- One task per subagent for focused execution.

### 3. Self-Improvement Loop
- After ANY correction from the user: update `tasks/lessons.md` with the pattern.
- Write rules for yourself that prevent the same mistake.
- Ruthlessly iterate on these lessons until mistake rate drops.
- Review lessons at session start for relevant project.

### 4. Verification Before Done
- Never mark a task complete without proving it works.
- Diff behavior between main and your changes when relevant.
- Ask yourself: "Would a staff engineer approve this?"
- Run tests, check logs, demonstrate correctness.

### 5. Demand Elegance (Balanced)
- For non-trivial changes: pause and ask "is there a more elegant way?"
- If a fix feels hacky: "Knowing everything I know now, implement the elegant solution."
- Skip this for simple, obvious fixes—don't over-engineer.
- Challenge your own work before presenting it.

### 6. Autonomous Bug Fixing
- When given a bug report: just fix it. Don't ask for hand-holding.
- Point at logs, errors, failing tests—then resolve them.
- Zero context switching required from the user.
- Go fix failing CI tests without being told how.

## Task Management
1. **Plan First**: Write plan to `tasks/todo.md` with checkable items.
2. **Verify Plan**: Check in before starting implementation.
3. **Track Progress**: Mark items complete as you go.
4. **Explain Changes**: High-level summary at each step.
5. **Document Results**: Add review section to `tasks/todo.md`.
6. **Capture Lessons**: Update `tasks/lessons.md` after corrections.

## Core Principles
- **Simplicity First**: Make every change as simple as possible. Impact minimal code.
- **No Laziness**: Find root causes. No temporary fixes. Senior developer standards.
- **Minimal Impact**: Changes should only touch what's necessary. Avoid introducing bugs.
