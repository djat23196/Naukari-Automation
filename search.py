from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout

from login import human_delay


@dataclass
class JobListing:
    title: str
    company: str
    job_id: str
    link: str
    element_index: int  # position on the current page (for clicking)


def build_search_url(
    keywords: str,
    location: str = "",
    experience_min: int = 0,
    experience_max: int = 50,
    freshness: int | None = None,
    page_number: int = 1,
) -> str:
    """Build a Naukri search results URL from filter parameters."""
    slug = re.sub(r"\s+", "-", keywords.strip().lower())
    base = f"https://www.naukri.com/{slug}-jobs"

    if location:
        loc_slug = re.sub(r"\s+", "-", location.strip().lower())
        base += f"-in-{loc_slug}"

    params: list[str] = []
    params.append(f"k={keywords.replace(' ', '+')}")
    params.append(f"l={location.replace(' ', '+')}")
    params.append(f"experience={experience_min}")
    params.append(f"nignbeam_7=1")  # sort by relevance

    if freshness:
        params.append(f"jobAge={freshness}")

    if page_number > 1:
        params.append(f"pageNo={page_number}")

    return base + "?" + "&".join(params)


def extract_job_listings(page: Page) -> List[JobListing]:
    """Extract all job cards from the current search results page."""
    listings: List[JobListing] = []

    job_cards = page.locator("article.jobTuple, .srp-jobtuple-wrapper, .cust-job-tuple")
    count = job_cards.count()

    if count == 0:
        job_cards = page.locator('[class*="jobTuple"], [data-job-id]')
        count = job_cards.count()

    for i in range(count):
        card = job_cards.nth(i)
        try:
            title_el = card.locator("a.title, [class*='jobTitle'] a, h2 a").first
            title = title_el.inner_text(timeout=3000).strip()
            link = title_el.get_attribute("href") or ""

            company_el = card.locator(
                "a.comp-name, a.subTitle, [class*='companyName']"
            ).first
            company = company_el.inner_text(timeout=3000).strip()

            job_id = card.get_attribute("data-job-id") or ""
            if not job_id:
                match = re.search(r"/job-listings?-.*?-(\d+)\b", link)
                job_id = match.group(1) if match else f"idx-{i}"

            listings.append(
                JobListing(
                    title=title,
                    company=company,
                    job_id=job_id,
                    link=link if link.startswith("http") else f"https://www.naukri.com{link}",
                    element_index=i,
                )
            )
        except (PlaywrightTimeout, Exception) as exc:
            print(f"  [!] Could not parse job card #{i}: {exc}")
            continue

    return listings


def search_jobs(page: Page, config: dict) -> List[JobListing]:
    """Navigate to the first page of search results and return listings."""
    url = build_search_url(
        keywords=config["keywords"],
        location=config.get("location", ""),
        experience_min=config.get("experience_min", 0),
        experience_max=config.get("experience_max", 50),
        freshness=config.get("freshness"),
        page_number=1,
    )
    print(f"[*] Searching: {url}")
    page.goto(url, wait_until="domcontentloaded")
    human_delay(2, 4)

    page.wait_for_selector(
        'article.jobTuple, [class*="jobTuple"], [data-job-id], .srp-jobtuple-wrapper',
        timeout=15_000,
    )

    listings = extract_job_listings(page)
    print(f"[+] Found {len(listings)} jobs on page 1")
    return listings


def go_to_next_page(page: Page, page_number: int, config: dict) -> bool:
    """Navigate to the next page of results. Returns True if successful."""
    url = build_search_url(
        keywords=config["keywords"],
        location=config.get("location", ""),
        experience_min=config.get("experience_min", 0),
        experience_max=config.get("experience_max", 50),
        freshness=config.get("freshness"),
        page_number=page_number,
    )
    print(f"[*] Going to page {page_number}...")
    page.goto(url, wait_until="domcontentloaded")
    human_delay(2, 4)

    try:
        page.wait_for_selector(
            'article.jobTuple, [class*="jobTuple"], [data-job-id], .srp-jobtuple-wrapper',
            timeout=10_000,
        )
        return True
    except PlaywrightTimeout:
        print(f"[!] No results found on page {page_number}")
        return False
