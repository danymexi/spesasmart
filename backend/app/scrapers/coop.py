"""Coop scraper -- navigates the interactive flyer viewer and extracts offers.

Source: https://www.coopalleanza3-0.it/ (Coop Alleanza 3.0) or regional portals.

Strategy:
    1. Open the Coop flyers page with Playwright.
    2. Locate the current promotional flyer for Lombardia.
    3. Navigate through the interactive viewer, screenshotting each page.
    4. Feed screenshots through the OCR + Gemini pipeline.
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import date
from pathlib import Path
from typing import Any

from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

from app.config import get_settings
from app.database import async_session
from app.models.chain import Chain
from app.models.flyer import Flyer
from app.scrapers.base import BaseScraper
from app.scrapers.pipeline import ScrapingPipeline

logger = logging.getLogger(__name__)

# Potential entry points for Coop flyers in Lombardia.
COOP_FLYER_URLS = [
    "https://www.cooplombardia.it/offerte-e-promozioni/volantino",
    "https://www.coopalleanza3-0.it/it/promozioni/volantino.html",
    "https://www.e-coop.it/promozioni",
]


class CoopScraper(BaseScraper):
    """Scraper for Coop Lombardia / Coop Alleanza 3.0 flyers."""

    name = "Coop"
    slug = "coop"
    base_url = "https://www.cooplombardia.it/offerte-e-promozioni/volantino"

    # Region target.
    TARGET_REGION = "Lombardia"
    TARGET_CITY = "Monza"

    def __init__(self) -> None:
        super().__init__()
        self.pipeline = ScrapingPipeline()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def scrape(self) -> list[dict[str, Any]]:
        """Execute the full Coop scraping workflow."""
        flyers_data: list[dict[str, Any]] = []

        try:
            page = await self._new_page()

            # Try each candidate URL until one works.
            working_url = await self._find_working_url(page)
            if working_url is None:
                logger.error("None of the Coop flyer URLs responded.")
                return []

            await self._accept_cookies(page)
            await page.wait_for_timeout(2000)

            # Try to select region / store.
            await self._select_region(page)

            # Find available flyers.
            flyer_entries = await self._find_flyer_entries(page)
            if not flyer_entries:
                logger.warning("No Coop flyers found.")
                return []

            for entry in flyer_entries:
                try:
                    flyer_data = await self._process_flyer_entry(page, entry)
                    if flyer_data:
                        flyers_data.append(flyer_data)
                except Exception:
                    logger.exception("Error processing Coop flyer: %s", entry.get("title"))

        except Exception:
            logger.exception("Coop scraping failed.")
        finally:
            await self.close()

        return flyers_data

    # ------------------------------------------------------------------
    # URL probing
    # ------------------------------------------------------------------

    async def _find_working_url(self, page: Page) -> str | None:
        """Try multiple Coop portal URLs and return the first that loads."""
        for url in COOP_FLYER_URLS:
            try:
                logger.info("Trying Coop URL: %s", url)
                resp = await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                if resp and resp.ok:
                    logger.info("Coop URL OK: %s", url)
                    self.base_url = url
                    return url
            except (PlaywrightTimeout, Exception):
                logger.debug("Coop URL failed: %s", url)
                continue
        return None

    # ------------------------------------------------------------------
    # Cookie consent
    # ------------------------------------------------------------------

    async def _accept_cookies(self, page: Page) -> None:
        selectors = [
            "button#onetrust-accept-btn-handler",
            "button:has-text('Accetta tutti')",
            "button:has-text('Accetta i cookie')",
            "button:has-text('Accetta')",
            "#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll",
        ]
        for sel in selectors:
            try:
                btn = page.locator(sel).first
                if await btn.is_visible(timeout=3000):
                    await btn.click()
                    await page.wait_for_timeout(1000)
                    return
            except (PlaywrightTimeout, Exception):
                continue

    # ------------------------------------------------------------------
    # Region / store selection
    # ------------------------------------------------------------------

    async def _select_region(self, page: Page) -> None:
        """Try to select Lombardia / Monza as the target region."""
        try:
            # Look for region or ZIP code selectors.
            region_selectors = [
                "button:has-text('Scegli punto vendita')",
                "button:has-text('Scegli negozio')",
                "a:has-text('Cambia punto vendita')",
                "[data-testid='store-selector']",
                ".store-selector-trigger",
            ]
            for sel in region_selectors:
                btn = page.locator(sel).first
                try:
                    if await btn.is_visible(timeout=3000):
                        await btn.click()
                        await page.wait_for_timeout(2000)
                        break
                except (PlaywrightTimeout, Exception):
                    continue

            # Fill search/postcode field.
            search_input = page.locator(
                "input[placeholder*='CAP'], "
                "input[placeholder*='cerca'], "
                "input[placeholder*='indirizzo'], "
                "input[type='search'], "
                "input[type='text']"
            ).first
            if await search_input.is_visible(timeout=3000):
                await search_input.fill(self.TARGET_CITY)
                await page.wait_for_timeout(2000)

                # Click the first suggestion.
                suggestion = page.locator(
                    f"li:has-text('{self.TARGET_CITY}'), "
                    f"div[role='option']:has-text('{self.TARGET_CITY}'), "
                    f".suggestion:has-text('{self.TARGET_CITY}')"
                ).first
                if await suggestion.is_visible(timeout=3000):
                    await suggestion.click()
                    await page.wait_for_timeout(2000)
                    logger.info("Selected Coop region: %s", self.TARGET_CITY)
                    return

            # Try a dropdown.
            selects = page.locator("select")
            count = await selects.count()
            for i in range(count):
                sel_el = selects.nth(i)
                options = await sel_el.locator("option").all_text_contents()
                for opt_text in options:
                    if self.TARGET_REGION.lower() in opt_text.lower() or self.TARGET_CITY.lower() in opt_text.lower():
                        await sel_el.select_option(label=opt_text)
                        await page.wait_for_timeout(2000)
                        logger.info("Selected region from dropdown: %s", opt_text)
                        return

        except (PlaywrightTimeout, Exception):
            logger.debug("Coop region selection failed -- using default.")

    # ------------------------------------------------------------------
    # Discover flyers
    # ------------------------------------------------------------------

    async def _find_flyer_entries(self, page: Page) -> list[dict[str, Any]]:
        """Find flyer links on the Coop page."""
        entries: list[dict[str, Any]] = []

        card_selectors = [
            "a[href*='volantino']",
            "a[href*='flyer']",
            "a[href*='promozioni']",
            ".flyer-card a",
            ".promo-item a",
            ".volantino-item a",
        ]

        seen: set[str] = set()
        for sel in card_selectors:
            links = page.locator(sel)
            count = await links.count()
            for i in range(count):
                link = links.nth(i)
                href = await link.get_attribute("href") or ""
                title = (await link.inner_text()).strip()[:200]
                if not href or href in seen:
                    continue

                full_url = href if href.startswith("http") else f"{self.base_url.rsplit('/', 1)[0]}/{href.lstrip('/')}"
                seen.add(full_url)

                valid_from, valid_to = self._extract_dates(title)
                entries.append(
                    {
                        "title": title or "Volantino Coop",
                        "url": full_url,
                        "valid_from": valid_from,
                        "valid_to": valid_to,
                    }
                )

        # If no explicit flyer links, treat the current page as the flyer.
        if not entries:
            entries.append(
                {
                    "title": "Volantino Coop",
                    "url": str(page.url),
                    "valid_from": None,
                    "valid_to": None,
                }
            )

        return entries

    # ------------------------------------------------------------------
    # Process a single flyer
    # ------------------------------------------------------------------

    async def _process_flyer_entry(
        self, parent_page: Page, entry: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Open flyer viewer, screenshot pages, run pipeline."""
        url = entry["url"]
        logger.info("Opening Coop flyer: %s", url)

        page = await self._new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded")
            await self._accept_cookies(page)
            await page.wait_for_timeout(3000)

            image_paths = await self._screenshot_flyer_pages(page, entry["title"])

            if not image_paths:
                # Fallback: take a single full-page screenshot.
                slug_title = re.sub(r"[^a-zA-Z0-9]+", "_", entry["title"])[:30].lower()
                fp = await self.save_screenshot(
                    page, filename=f"{slug_title}_full.png", full_page=True
                )
                image_paths = [fp]

            result = {
                "chain": self.name,
                "slug": self.slug,
                "title": entry["title"],
                "source_url": url,
                "valid_from": entry.get("valid_from") or date.today(),
                "valid_to": entry.get("valid_to") or date.today(),
                "image_paths": [str(p) for p in image_paths],
            }

            await self._persist_and_extract(result)
            return result

        finally:
            await page.close()

    # ------------------------------------------------------------------
    # Flyer viewer navigation + screenshots
    # ------------------------------------------------------------------

    async def _screenshot_flyer_pages(
        self, page: Page, flyer_title: str
    ) -> list[Path]:
        """Navigate through the interactive flyer viewer, capturing each page."""
        paths: list[Path] = []
        slug_title = re.sub(r"[^a-zA-Z0-9]+", "_", flyer_title)[:30].strip("_").lower()
        max_pages = 60

        # Wait for viewer to initialise.
        await page.wait_for_timeout(3000)

        # Try to detect if the page contains an embedded viewer (iframe).
        iframe_locator = page.locator("iframe[src*='viewer'], iframe[src*='flyer'], iframe[src*='volantino']").first
        viewer_page = page
        try:
            if await iframe_locator.is_visible(timeout=5000):
                frame = iframe_locator.content_frame
                if frame is not None:
                    logger.info("Detected embedded flyer viewer iframe.")
                    # We cannot screenshot a frame directly -- use the parent
                    # page but try to make the iframe fullscreen.
                    try:
                        await page.evaluate("""
                            const iframe = document.querySelector('iframe');
                            if (iframe) {
                                iframe.style.position = 'fixed';
                                iframe.style.top = '0';
                                iframe.style.left = '0';
                                iframe.style.width = '100vw';
                                iframe.style.height = '100vh';
                                iframe.style.zIndex = '9999';
                            }
                        """)
                        await page.wait_for_timeout(1000)
                    except Exception:
                        pass
        except (PlaywrightTimeout, Exception):
            pass

        for page_num in range(1, max_pages + 1):
            filename = f"{slug_title}_p{page_num:03d}.png"
            path = await self.save_screenshot(
                viewer_page, filename=filename, full_page=False
            )
            paths.append(path)

            advanced = await self._advance_page(viewer_page)
            if not advanced:
                logger.info("Reached last page (%d) of Coop flyer.", page_num)
                break

        return paths

    async def _advance_page(self, page: Page) -> bool:
        """Try to navigate to the next flyer page."""
        next_selectors = [
            "button[aria-label*='next' i]",
            "button[aria-label*='avanti' i]",
            "button[aria-label*='prossim' i]",
            ".btn-next",
            ".next-page",
            "[data-action='next']",
            "button:has-text('>')",
            "button:has-text('Avanti')",
            ".arrow-right",
            ".icon-arrow-right",
        ]
        for sel in next_selectors:
            try:
                btn = page.locator(sel).first
                if await btn.is_visible(timeout=1500):
                    if await btn.is_enabled():
                        await btn.click()
                        await page.wait_for_timeout(1500)
                        return True
                    else:
                        return False
            except (PlaywrightTimeout, Exception):
                continue

        # Fallback: keyboard navigation.
        try:
            await page.keyboard.press("ArrowRight")
            await page.wait_for_timeout(1500)
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Database persistence
    # ------------------------------------------------------------------

    async def _persist_and_extract(self, flyer_data: dict[str, Any]) -> None:
        """Create Flyer row and run extraction pipeline."""
        async with async_session() as session:
            from sqlalchemy import select

            stmt = select(Chain).where(Chain.slug == self.slug)
            result = await session.execute(stmt)
            chain = result.scalar_one_or_none()

            if chain is None:
                logger.error("Chain '%s' not found in DB.", self.slug)
                return

            flyer = Flyer(
                chain_id=chain.id,
                title=flyer_data["title"],
                valid_from=flyer_data["valid_from"],
                valid_to=flyer_data["valid_to"],
                source_url=flyer_data["source_url"],
                pages_count=len(flyer_data["image_paths"]),
                status="processing",
            )
            session.add(flyer)
            await session.commit()
            await session.refresh(flyer)

            flyer_id = flyer.id
            chain_id = chain.id

        await self.pipeline.process_flyer(
            flyer_id=flyer_id,
            image_paths=flyer_data["image_paths"],
            chain_name=self.name,
            chain_id=chain_id,
        )

    # ------------------------------------------------------------------
    # Date parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_dates(text: str) -> tuple[date | None, date | None]:
        """Parse Italian date ranges from flyer titles."""
        patterns = [
            r"dal?\s+(\d{1,2})[/.](\d{1,2})[/.](\d{4})\s+al?\s+(\d{1,2})[/.](\d{1,2})[/.](\d{4})",
            r"dal?\s+(\d{1,2})[/.](\d{1,2})\s+al?\s+(\d{1,2})[/.](\d{1,2})[/.](\d{4})",
            r"(\d{1,2})[/.](\d{1,2})\s*[-–]\s*(\d{1,2})[/.](\d{1,2})[/.](\d{4})",
        ]
        for pattern in patterns:
            m = re.search(pattern, text, re.IGNORECASE)
            if not m:
                continue
            groups = m.groups()
            try:
                if len(groups) == 6:
                    vf = date(int(groups[2]), int(groups[1]), int(groups[0]))
                    vt = date(int(groups[5]), int(groups[4]), int(groups[3]))
                    return vf, vt
                elif len(groups) == 5:
                    year = int(groups[4])
                    vf = date(year, int(groups[1]), int(groups[0]))
                    vt = date(year, int(groups[3]), int(groups[2]))
                    return vf, vt
            except (ValueError, IndexError):
                continue
        return None, None
