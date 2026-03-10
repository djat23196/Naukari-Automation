import logging
import random
import time

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout

logger = logging.getLogger(__name__)


LOGIN_URL = "https://www.naukri.com/nlogin/login"
DASHBOARD_URL_FRAGMENT = "naukri.com/mnjuser/homepage"


def human_delay(min_sec: float = 1.0, max_sec: float = 3.0):
    time.sleep(random.uniform(min_sec, max_sec))


def human_type(page: Page, locator, text: str):
    """Type text character by character with random delays to mimic human typing."""
    if locator is None:
        raise ValueError("human_type: locator is None")
    locator.click()
    for char in text:
        page.keyboard.type(char)
        time.sleep(random.uniform(0.05, 0.15))


def dismiss_popups(page: Page):
    """Close common popups that appear after login (profile nudges, etc.)."""
    popup_close_selectors = [
        'button:has-text("Not now")',
        'button:has-text("Maybe later")',
        'button:has-text("No thanks")',
        ".crossIcon",
        '[class*="crossIcon"]',
        ".modal-close",
    ]
    for sel in popup_close_selectors:
        try:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=800):
                btn.click()
                human_delay(0.5, 1.0)
        except (PlaywrightTimeout, Exception):
            continue


def login(page: Page, email: str, password: str) -> bool:
    """Log in to Naukri.com. Returns True on success."""
    logger.info("Navigating to Naukri login page...")
    page.goto(LOGIN_URL, wait_until="domcontentloaded")
    human_delay()

    logger.info("Filling credentials...")
    # Target the login form inputs specifically to avoid matching the navbar search bar
    email_input = page.locator('form input[placeholder*="Email" i], form input[type="text"][placeholder*="ID" i]').first
    human_type(page, email_input, email)
    human_delay(0.5, 1.5)

    password_input = page.locator('form input[type="password"]').first
    human_type(page, password_input, password)
    human_delay(0.5, 1.0)

    logger.info("Clicking login button...")
    login_btn = page.locator(
        'button:has-text("Login"), button[type="submit"]'
    ).first
    login_btn.click()

    logger.info("Waiting for dashboard to load...")
    try:
        page.wait_for_url(f"**/{DASHBOARD_URL_FRAGMENT}**", timeout=30_000)
    except PlaywrightTimeout:
        if "login" in page.url.lower():
            logger.warning("Login may have failed — still on login page.")
            return False

    human_delay()
    dismiss_popups(page)

    # Final validation: ensure we're actually on the dashboard
    if DASHBOARD_URL_FRAGMENT not in page.url.lower():
        logger.error(f"Login validation failed. Expected dashboard URL fragment '{DASHBOARD_URL_FRAGMENT}', but got: {page.url}")
        return False

    logger.info("Login successful!")
    return True
