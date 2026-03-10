#!/usr/bin/env python3
"""Naukri.com Auto-Apply Bot — searches for jobs and applies automatically."""

import argparse
import json
import logging
import os
import random
import sys

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

_stealth = Stealth()

from answer_engine import validate_api_keys
from apply import apply_to_jobs
from login import login
from playwright._impl._errors import TargetClosedError

from search import extract_job_listings, go_to_next_page, search_jobs

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
SESSION_FILE = ".session.json"


def setup_logging(debug: bool = False, log_file: str | None = None):
    """Configure logging for the application."""
    level = logging.DEBUG if debug else logging.INFO
    fmt = "[%(asctime)s] %(levelname)s %(message)s"
    datefmt = "%H:%M:%S"

    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if log_file:
        handlers.append(logging.FileHandler(log_file))

    logging.basicConfig(level=level, format=fmt, datefmt=datefmt, handlers=handlers)


def load_config(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_profile(path: str = ".profile.json") -> dict:
    """Load profile from separate file. Falls back to config.json profile."""
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def validate_config(config: dict) -> tuple[bool, str]:
    """Validate config structure and required fields."""
    required = ["keywords"]
    for key in required:
        if key not in config:
            return False, f"Missing required config key: '{key}'"

    if not isinstance(config["keywords"], (list, str)):
        return False, "config 'keywords' must be a string or list of strings"

    exp_min = config.get("experience_min", 0)
    exp_max = config.get("experience_max", 50)
    if not isinstance(exp_min, int) or exp_min < 0:
        return False, "experience_min must be a non-negative integer"
    if not isinstance(exp_max, int) or exp_max < exp_min:
        return False, "experience_max must be >= experience_min"

    max_pages = config.get("max_pages", 5)
    if not isinstance(max_pages, int) or max_pages < 1:
        return False, "max_pages must be >= 1"

    max_apps = config.get("max_applications_per_day", 50)
    if not isinstance(max_apps, int) or max_apps < 1:
        return False, "max_applications_per_day must be >= 1"

    return True, "Config valid"


def create_context(browser, storage_state=None):
    """Create a new browser context with standard settings."""
    kwargs = {
        "viewport": {"width": 1280, "height": 800},
        "user_agent": USER_AGENT,
    }
    if storage_state and os.path.exists(storage_state):
        kwargs["storage_state"] = storage_state
    context = browser.new_context(**kwargs)
    _stealth.apply_stealth_sync(context)
    return context


def main():
    parser = argparse.ArgumentParser(description="Naukri Auto-Apply Bot")
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode")
    parser.add_argument("--config", default="config.json", help="Path to config file")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--log-file", default="naukri_bot.log", help="Log file path")
    parser.add_argument("--force-login", action="store_true", help="Force re-login (ignore saved session)")
    args = parser.parse_args()

    # Logging
    setup_logging(debug=args.debug, log_file=args.log_file)

    # Environment
    load_dotenv()
    email = os.getenv("NAUKRI_EMAIL", "")
    password = os.getenv("NAUKRI_PASSWORD", "")
    if not email or not password:
        logger.error("Set NAUKRI_EMAIL and NAUKRI_PASSWORD in your .env file.")
        sys.exit(1)

    # Config
    config = load_config(args.config)
    valid, msg = validate_config(config)
    if not valid:
        logger.error(f"Config validation failed: {msg}")
        sys.exit(1)
    logger.debug(f"Config loaded: {msg}")

    # Profile (separate file, fallback to config.json)
    profile = load_profile(".profile.json")
    if profile:
        config["profile"] = profile
        logger.info("Profile loaded from .profile.json")
    elif "profile" not in config:
        logger.warning("No profile found — chatbot answers may use defaults")

    # API keys
    keys_ok, keys_msg = validate_api_keys()
    if not keys_ok:
        logger.error(keys_msg)
        sys.exit(1)
    logger.info(keys_msg)

    max_pages = config.get("max_pages", 5)
    context_recycle_every = config.get("context_recycle_every", 15)
    total_summary = {"applied": 0, "skipped_external": 0, "already_applied": 0, "failed": 0}

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=args.headless,
            args=["--disable-blink-features=AutomationControlled"],
        )

        # Session persistence: try loading saved session
        use_saved_session = (
            not args.force_login
            and os.path.exists(SESSION_FILE)
        )

        context = create_context(
            browser,
            storage_state=SESSION_FILE if use_saved_session else None,
        )
        page = context.new_page()

        # Login (skip if we have a valid session)
        if use_saved_session:
            logger.info("Using saved session from .session.json")
            # Verify session is still valid by navigating to dashboard
            page.goto("https://www.naukri.com/mnjuser/homepage", wait_until="domcontentloaded")
            from login import human_delay
            human_delay(2, 4)
            if "login" in page.url.lower():
                logger.warning("Saved session expired — logging in fresh")
                use_saved_session = False

        if not use_saved_session:
            if not login(page, email, password):
                logger.error("Login failed. Exiting.")
                browser.close()
                sys.exit(1)
            # Save session for next run
            context.storage_state(path=SESSION_FILE)
            logger.info("Session saved to .session.json")

        # Build search combinations
        keywords_list = config["keywords"]
        if isinstance(keywords_list, str):
            keywords_list = [keywords_list]

        locations_list = config.get("location", [""])
        if isinstance(locations_list, str):
            locations_list = [locations_list]

        searches = [(kw, loc) for kw in keywords_list for loc in locations_list]
        random.shuffle(searches)
        total_searches = len(searches)
        seen_jobs: set[tuple[str, str]] = set()
        context_app_count = 0

        for search_idx, (keyword, location) in enumerate(searches, 1):
            logger.info(f"\n{'='*50}")
            logger.info(f"  SEARCH {search_idx}/{total_searches}: {keyword} in {location or 'Any'}")
            logger.info(f"{'='*50}")

            search_config = {**config, "keywords": keyword, "location": location}
            try:
                jobs = search_jobs(page, search_config)
            except TargetClosedError:
                logger.warning("Page closed before search — recreating...")
                page = context.new_page()
                jobs = search_jobs(page, search_config)

            for page_num in range(1, max_pages + 1):
                if page_num > 1:
                    try:
                        has_next = go_to_next_page(page, page_num, search_config)
                    except TargetClosedError:
                        logger.warning("Page closed before pagination — recreating...")
                        page = context.new_page()
                        has_next = go_to_next_page(page, page_num, search_config)
                    if not has_next:
                        logger.info(f"No more pages after page {page_num - 1}.")
                        break
                    jobs = extract_job_listings(page)
                    logger.info(f"Found {len(jobs)} jobs on page {page_num}")

                if not jobs:
                    logger.info(f"No jobs found on page {page_num}. Stopping.")
                    break

                page_summary = apply_to_jobs(page, jobs, config, seen_jobs=seen_jobs)
                for key in total_summary:
                    total_summary[key] += page_summary[key]

                # Recover if page was closed during apply (e.g. by Naukri's JS)
                if page.is_closed():
                    logger.warning("Page was closed during applications — recreating...")
                    try:
                        page = context.new_page()
                    except Exception:
                        logger.warning("Context also closed — recreating context...")
                        context = create_context(browser, storage_state=SESSION_FILE)
                        page = context.new_page()
                        context_app_count = 0

                # Context rotation
                context_app_count += page_summary["applied"]
                if context_app_count >= context_recycle_every:
                    logger.info(f"Recycling browser context after {context_app_count} applications...")
                    context.storage_state(path=SESSION_FILE)
                    context.close()
                    context = create_context(browser, storage_state=SESSION_FILE)
                    page = context.new_page()
                    context_app_count = 0

        browser.close()

    logger.info(f"\n{'='*50}")
    logger.info("             APPLICATION SUMMARY")
    logger.info(f"{'='*50}")
    logger.info(f"  Applied:          {total_summary['applied']}")
    logger.info(f"  Skipped (ext):    {total_summary['skipped_external']}")
    logger.info(f"  Already applied:  {total_summary['already_applied']}")
    logger.info(f"  Failed:           {total_summary['failed']}")
    total = sum(total_summary.values())
    logger.info(f"  Total processed:  {total}")
    logger.info(f"{'='*50}")


if __name__ == "__main__":
    main()
