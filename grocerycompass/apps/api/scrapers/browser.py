"""Stealth browser configuration for Playwright-based scrapers."""

import random

from scrapers.base import USER_AGENTS


async def get_stealth_browser():
    """Create a Playwright browser context with anti-detection measures."""
    from playwright.async_api import async_playwright

    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(
        headless=True,
        args=[
            '--disable-blink-features=AutomationControlled',
            '--no-sandbox',
        ]
    )
    context = await browser.new_context(
        user_agent=random.choice(USER_AGENTS),
        viewport={'width': 1366, 'height': 768},
        locale='it-IT',
        timezone_id='Europe/Rome',
        geolocation={'latitude': 45.4642, 'longitude': 9.1900},
        permissions=['geolocation']
    )
    # Inject anti-fingerprint script
    await context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined})
    """)
    return playwright, browser, context


async def close_browser(playwright, browser):
    """Clean up browser resources."""
    await browser.close()
    await playwright.stop()
