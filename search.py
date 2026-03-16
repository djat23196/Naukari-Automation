from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from typing import List
from urllib.parse import quote_plus

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout

from login import human_delay

logger = logging.getLogger(__name__)


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
    params.append(f"k={quote_plus(keywords)}")
    params.append(f"l={quote_plus(location)}")
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
                if match:
                    job_id = match.group(1)
                else:
                    job_id = hashlib.md5(link.encode()).hexdigest()[:16]

            listings.append(
                JobListing(
                    title=title,
                    company=company,
                    job_id=job_id,
                    link=link if link.startswith("http") else f"https://www.naukri.com{link}",
                    element_index=i,
                )
            )
        except PlaywrightTimeout:
            logger.debug(f"Timeout parsing job card #{i}")
            continue
        except Exception as exc:
            logger.warning(f"Error parsing job card #{i}: {exc}")
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
    logger.info(f"Searching: {url}")
    page.goto(url, wait_until="domcontentloaded")
    human_delay(2, 4)

    page.wait_for_selector(
        'article.jobTuple, [class*="jobTuple"], [data-job-id], .srp-jobtuple-wrapper',
        timeout=15_000,
    )

    listings = extract_job_listings(page)
    logger.info(f"Found {len(listings)} jobs on page 1")
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
    logger.info(f"Going to page {page_number}...")
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=45_000)
    except (PlaywrightTimeout, Exception) as exc:
        logger.warning(f"Page {page_number} navigation failed: {exc}")
        return False
    human_delay(2, 4)

    try:
        page.wait_for_selector(
            'article.jobTuple, [class*="jobTuple"], [data-job-id], .srp-jobtuple-wrapper',
            timeout=10_000,
        )
        return True
    except PlaywrightTimeout:
        logger.warning(f"No results found on page {page_number}")
        return False
