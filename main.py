#!/usr/bin/env python3
"""Naukri.com Auto-Apply Bot — searches for jobs and applies automatically."""

import argparse
import json
import os
import sys

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

from apply import apply_to_jobs
from login import login
from search import extract_job_listings, go_to_next_page, search_jobs


def load_config(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main():
    parser = argparse.ArgumentParser(description="Naukri Auto-Apply Bot")
    parser.add_argument(
        "--headless", action="store_true", help="Run browser in headless mode"
    )
    parser.add_argument(
        "--config", default="config.json", help="Path to config file (default: config.json)"
    )
    args = parser.parse_args()

    load_dotenv()
    email = os.getenv("NAUKRI_EMAIL", "")
    password = os.getenv("NAUKRI_PASSWORD", "")
    if not email or not password:
        print("[!] Set NAUKRI_EMAIL and NAUKRI_PASSWORD in your .env file.")
        sys.exit(1)

    config = load_config(args.config)
    max_pages = config.get("max_pages", 5)

    total_summary = {"applied": 0, "skipped_external": 0, "already_applied": 0, "failed": 0}

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=args.headless)
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()

        if not login(page, email, password):
            print("[!] Login failed. Exiting.")
            browser.close()
            sys.exit(1)

        # Support both single string and list for keywords/location
        keywords_list = config["keywords"]
        if isinstance(keywords_list, str):
            keywords_list = [keywords_list]

        locations_list = config.get("location", [""])
        if isinstance(locations_list, str):
            locations_list = [locations_list]

        # Build all search combinations and shuffle to avoid predictable patterns
        import random
        searches = [(kw, loc) for kw in keywords_list for loc in locations_list]
        random.shuffle(searches)
        total_searches = len(searches)
        seen_jobs: set[tuple[str, str]] = set()  # persist across all searches

        for search_idx, (keyword, location) in enumerate(searches, 1):
            print(f"\n{'='*50}")
            print(f"  SEARCH {search_idx}/{total_searches}: {keyword} in {location or 'Any'}")
            print(f"{'='*50}")

            search_config = {**config, "keywords": keyword, "location": location}
            jobs = search_jobs(page, search_config)

            for page_num in range(1, max_pages + 1):
                if page_num > 1:
                    if not go_to_next_page(page, page_num, search_config):
                        print(f"[*] No more pages after page {page_num - 1}.")
                        break
                    jobs = extract_job_listings(page)
                    print(f"[+] Found {len(jobs)} jobs on page {page_num}")

                if not jobs:
                    print(f"[*] No jobs found on page {page_num}. Stopping.")
                    break

                page_summary = apply_to_jobs(page, jobs, config, seen_jobs=seen_jobs)
                for key in total_summary:
                    total_summary[key] += page_summary[key]

        browser.close()

    print("\n" + "=" * 50)
    print("             APPLICATION SUMMARY")
    print("=" * 50)
    print(f"  Applied:          {total_summary['applied']}")
    print(f"  Skipped (ext):    {total_summary['skipped_external']}")
    print(f"  Already applied:  {total_summary['already_applied']}")
    print(f"  Failed:           {total_summary['failed']}")
    total = sum(total_summary.values())
    print(f"  Total processed:  {total}")
    print("=" * 50)


if __name__ == "__main__":
    main()
