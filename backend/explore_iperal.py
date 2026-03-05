"""Explore Iperal Spesa Online API endpoints by intercepting network requests."""

import asyncio
import json
from playwright.async_api import async_playwright

IPERAL_URL = "https://www.iperalspesaonline.it/"
EMAIL = "danymexi@me.com"
PASSWORD = "Dublino.2"


async def main():
    api_calls = []

    async def on_response(response):
        url = response.url
        content_type = response.headers.get("content-type", "")

        # Only log API/JSON calls, skip static assets
        if any(skip in url for skip in [".js", ".css", ".png", ".jpg", ".svg", ".woff", ".ico", "google", "facebook", "analytics", "gtag", "gtm"]):
            return

        if "json" in content_type or "api" in url.lower() or "/rest/" in url.lower() or "/graphql" in url.lower():
            status = response.status
            try:
                body = await response.text()
                # Truncate large bodies
                preview = body[:2000] if len(body) > 2000 else body
            except Exception:
                preview = "<could not read body>"

            entry = {
                "url": url,
                "status": status,
                "content_type": content_type,
                "body_length": len(body) if 'body' in dir() else 0,
                "preview": preview,
            }
            api_calls.append(entry)
            print(f"\n{'='*80}")
            print(f"API CALL: {status} {url}")
            print(f"Content-Type: {content_type}")
            print(f"Body length: {entry['body_length']}")
            print(f"Preview: {preview[:500]}")

    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=True)
    context = await browser.new_context(
        viewport={"width": 1920, "height": 1080},
        locale="it-IT",
        timezone_id="Europe/Rome",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    )
    context.set_default_timeout(30000)

    page = await context.new_page()
    page.on("response", on_response)

    # Step 1: Navigate to the site
    print("\n>>> Navigating to Iperal Spesa Online...")
    await page.goto(IPERAL_URL, wait_until="domcontentloaded")
    await page.wait_for_timeout(5000)

    # Take screenshot of landing page
    await page.screenshot(path="/tmp/iperal_01_landing.png", full_page=False)
    print(f"\n>>> Current URL: {page.url}")
    print(f">>> Page title: {await page.title()}")

    # Step 2: Accept cookies if present
    print("\n>>> Looking for cookie banner...")
    cookie_selectors = [
        "button:has-text('Accetta')",
        "button:has-text('Accept')",
        "button:has-text('OK')",
        "#onetrust-accept-btn-handler",
        "button[id*='cookie']",
        ".cookie-accept",
    ]
    for sel in cookie_selectors:
        try:
            btn = page.locator(sel).first
            if await btn.is_visible(timeout=2000):
                await btn.click()
                print(f">>> Clicked cookie consent: {sel}")
                await page.wait_for_timeout(1000)
                break
        except Exception:
            continue

    # Step 3: Look for login elements
    print("\n>>> Looking for login form or button...")
    await page.screenshot(path="/tmp/iperal_02_after_cookies.png", full_page=False)

    # Try to find login button/link
    login_selectors = [
        "a:has-text('Accedi')",
        "a:has-text('Login')",
        "button:has-text('Accedi')",
        "button:has-text('Login')",
        "[class*='login']",
        "[class*='accedi']",
        "a[href*='login']",
        "a[href*='accedi']",
        "a[href*='account']",
        ".user-icon",
        "[class*='user']",
        "[data-testid*='login']",
    ]

    for sel in login_selectors:
        try:
            el = page.locator(sel).first
            if await el.is_visible(timeout=2000):
                print(f">>> Found login element: {sel}")
                text = await el.inner_text()
                print(f"    Text: {text[:100]}")
                await el.click()
                await page.wait_for_timeout(3000)
                await page.screenshot(path="/tmp/iperal_03_login_click.png", full_page=False)
                print(f">>> URL after click: {page.url}")
                break
        except Exception:
            continue

    # Step 4: Try to fill login form
    print("\n>>> Looking for email/password fields...")
    email_selectors = [
        "input[type='email']",
        "input[name='email']",
        "input[name='username']",
        "input[placeholder*='email' i]",
        "input[placeholder*='utente' i]",
        "input[id*='email' i]",
        "input[id*='user' i]",
    ]
    password_selectors = [
        "input[type='password']",
        "input[name='password']",
        "input[placeholder*='password' i]",
    ]

    email_filled = False
    for sel in email_selectors:
        try:
            el = page.locator(sel).first
            if await el.is_visible(timeout=3000):
                await el.fill(EMAIL)
                print(f">>> Filled email with: {sel}")
                email_filled = True
                break
        except Exception:
            continue

    if email_filled:
        for sel in password_selectors:
            try:
                el = page.locator(sel).first
                if await el.is_visible(timeout=2000):
                    await el.fill(PASSWORD)
                    print(f">>> Filled password with: {sel}")
                    break
            except Exception:
                continue

        await page.screenshot(path="/tmp/iperal_04_login_filled.png", full_page=False)

        # Submit the form
        submit_selectors = [
            "button[type='submit']",
            "button:has-text('Accedi')",
            "button:has-text('Login')",
            "button:has-text('Entra')",
            "input[type='submit']",
        ]
        for sel in submit_selectors:
            try:
                btn = page.locator(sel).first
                if await btn.is_visible(timeout=2000):
                    await btn.click()
                    print(f">>> Clicked submit: {sel}")
                    await page.wait_for_timeout(5000)
                    break
            except Exception:
                continue

        await page.screenshot(path="/tmp/iperal_05_after_login.png", full_page=False)
        print(f">>> URL after login: {page.url}")
        print(f">>> Page title: {await page.title()}")

    # Step 5: Explore the site structure - look for categories/navigation
    print("\n>>> Exploring site navigation...")
    await page.wait_for_timeout(3000)

    # Try to find category navigation
    nav_selectors = [
        "nav a",
        "[class*='category'] a",
        "[class*='menu'] a",
        "[class*='nav'] a",
        ".sidebar a",
        "[class*='department'] a",
        "[class*='reparto'] a",
    ]

    found_links = []
    for sel in nav_selectors:
        try:
            links = page.locator(sel)
            count = await links.count()
            if count > 2:
                print(f"\n>>> Found {count} links with selector: {sel}")
                for i in range(min(count, 20)):
                    text = (await links.nth(i).inner_text()).strip()
                    href = await links.nth(i).get_attribute("href") or ""
                    if text and len(text) > 1:
                        found_links.append({"text": text[:80], "href": href[:200]})
                        print(f"    [{i}] {text[:80]} -> {href[:100]}")
                if found_links:
                    break
        except Exception:
            continue

    # Step 6: Try navigating to a category to trigger product API calls
    if found_links:
        # Pick first category-like link
        for link in found_links:
            if any(kw in link["text"].lower() for kw in ["frutta", "verdura", "latte", "pane", "carne", "pesce", "pasta"]):
                target = link
                break
        else:
            target = found_links[0]

        print(f"\n>>> Navigating to category: {target['text']} ({target['href']})")
        try:
            href = target["href"]
            if href and not href.startswith("javascript"):
                if href.startswith("/"):
                    href = f"https://www.iperalspesaonline.it{href}"
                await page.goto(href, wait_until="domcontentloaded")
                await page.wait_for_timeout(5000)
                await page.screenshot(path="/tmp/iperal_06_category.png", full_page=False)
                print(f">>> Category page URL: {page.url}")

                # Scroll to load more products
                for i in range(3):
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await page.wait_for_timeout(2000)
        except Exception as e:
            print(f">>> Error navigating to category: {e}")
    else:
        # Try clicking on visible elements that look like categories
        print("\n>>> No nav links found, trying to find clickable categories...")
        await page.screenshot(path="/tmp/iperal_06_no_nav.png", full_page=True)

        # Try search
        search_selectors = [
            "input[type='search']",
            "input[placeholder*='cerca' i]",
            "input[placeholder*='search' i]",
            "[class*='search'] input",
        ]
        for sel in search_selectors:
            try:
                el = page.locator(sel).first
                if await el.is_visible(timeout=3000):
                    print(f">>> Found search field: {sel}")
                    await el.fill("latte")
                    await page.keyboard.press("Enter")
                    await page.wait_for_timeout(5000)
                    await page.screenshot(path="/tmp/iperal_07_search.png", full_page=False)
                    print(f">>> Search URL: {page.url}")
                    break
            except Exception:
                continue

    # Step 7: Dump all collected API calls
    print(f"\n\n{'='*80}")
    print(f"SUMMARY: {len(api_calls)} API calls intercepted")
    print(f"{'='*80}")
    for i, call in enumerate(api_calls):
        print(f"\n[{i+1}] {call['status']} {call['url']}")
        print(f"    Type: {call['content_type']}")
        print(f"    Size: {call['body_length']} bytes")

    # Save full results to file
    with open("/tmp/iperal_api_calls.json", "w") as f:
        json.dump(api_calls, f, indent=2, default=str)
    print("\n>>> Full API data saved to /tmp/iperal_api_calls.json")

    # Get all cookies (for auth tokens)
    cookies = await context.cookies()
    auth_cookies = [c for c in cookies if any(kw in c["name"].lower() for kw in ["token", "auth", "session", "jwt", "sid"])]
    print(f"\n>>> Auth-related cookies: {len(auth_cookies)}")
    for c in auth_cookies:
        print(f"    {c['name']} = {c['value'][:50]}...")

    await browser.close()
    await pw.stop()


if __name__ == "__main__":
    asyncio.run(main())
