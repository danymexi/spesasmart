"""Esselunga scraper -- navigates the interactive flyer viewer and extracts offers.

Source: https://www.esselunga.it/it-it/promozioni/volantini.html

Strategy:
    1. Open the flyers page with Playwright.
    2. Select the Monza e Brianza store/area.
    3. Open the current flyer in the interactive viewer.
    4. Iterate through pages, taking high-resolution screenshots.
    5. Feed each screenshot through the OCR + Gemini pipeline.
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import date, datetime
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


class EsselungaScraper(BaseScraper):
    """Scraper for Esselunga supermarket flyers."""

    name = "Esselunga"
    slug = "esselunga"
    base_url = "https://www.esselunga.it/it-it/promozioni/volantini.html"

    # Target area for flyer selection.
    TARGET_AREA = "Monza"

    def __init__(self) -> None:
        super().__init__()
        self.pipeline = ScrapingPipeline()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def scrape(self) -> list[dict[str, Any]]:
        """Execute the full Esselunga scraping workflow.

        Returns a list of flyer metadata dicts, each with an ``image_paths``
        key pointing to the downloaded page screenshots.
        """
        flyers_data: list[dict[str, Any]] = []

        try:
            page = await self._new_page()
            logger.info("Navigating to Esselunga flyers page: %s", self.base_url)
            await page.goto(self.base_url, wait_until="domcontentloaded")

            # Handle cookie consent banner if present.
            await self._accept_cookies(page)

            # Select the target store / area.
            await self._select_store_area(page)

            # Gather flyer links from the page.
            flyer_entries = await self._find_flyer_entries(page)
            if not flyer_entries:
                logger.warning("No flyers found on Esselunga page.")
                return []

            for entry in flyer_entries:
                try:
                    flyer_data = await self._process_flyer_entry(page, entry)
                    if flyer_data:
                        flyers_data.append(flyer_data)
                except Exception:
                    logger.exception(
                        "Error processing Esselunga flyer entry: %s", entry
                    )

        except Exception:
            logger.exception("Esselunga scraping failed.")
        finally:
            await self.close()

        return flyers_data

    # ------------------------------------------------------------------
    # Cookie consent
    # ------------------------------------------------------------------

    async def _accept_cookies(self, page: Page) -> None:
        """Dismiss cookie consent dialogs."""
        selectors = [
            "button#onetrust-accept-btn-handler",
            "button:has-text('Accetta tutti')",
            "button:has-text('Accetta')",
        ]
        for sel in selectors:
            try:
                btn = page.locator(sel).first
                if await btn.is_visible(timeout=3000):
                    await btn.click()
                    logger.debug("Cookie consent accepted via: %s", sel)
                    await page.wait_for_timeout(1000)
                    return
            except (PlaywrightTimeout, Exception):
                continue

    # ------------------------------------------------------------------
    # Store / area selection
    # ------------------------------------------------------------------

    async def _select_store_area(self, page: Page) -> None:
        """Attempt to select the Monza e Brianza region/store.

        Esselunga may show a store-selector overlay or a dropdown.  We try
        multiple strategies to pick the correct area.
        """
        try:
            # Strategy 1: Look for a location/store selector button.
            store_btn = page.locator(
                "button:has-text('punto vendita'), "
                "button:has-text('negozio'), "
                "a:has-text('Seleziona punto vendita'), "
                "[data-testid='store-selector']"
            ).first
            if await store_btn.is_visible(timeout=5000):
                await store_btn.click()
                await page.wait_for_timeout(2000)

                # Type the target area into the search field if available.
                search_input = page.locator(
                    "input[placeholder*='cerca'], "
                    "input[placeholder*='indirizzo'], "
                    "input[type='search']"
                ).first
                if await search_input.is_visible(timeout=3000):
                    await search_input.fill(self.TARGET_AREA)
                    await page.wait_for_timeout(2000)

                # Click the first matching result.
                result = page.locator(
                    f"li:has-text('{self.TARGET_AREA}'), "
                    f"div:has-text('{self.TARGET_AREA}')"
                ).first
                if await result.is_visible(timeout=3000):
                    await result.click()
                    await page.wait_for_timeout(2000)
                    logger.info("Selected store area: %s", self.TARGET_AREA)
                    return

            # Strategy 2: Dropdown-based selector.
            dropdown = page.locator("select").first
            if await dropdown.is_visible(timeout=3000):
                options = await dropdown.locator("option").all_text_contents()
                for opt in options:
                    if self.TARGET_AREA.lower() in opt.lower():
                        await dropdown.select_option(label=opt)
                        await page.wait_for_timeout(2000)
                        logger.info("Selected area from dropdown: %s", opt)
                        return

        except (PlaywrightTimeout, Exception):
            logger.debug(
                "Store selector not found or interaction failed -- "
                "continuing with default location."
            )

    # ------------------------------------------------------------------
    # Discover available flyers
    # ------------------------------------------------------------------

    async def _find_flyer_entries(self, page: Page) -> list[dict[str, Any]]:
        """Identify flyer cards / links on the page.

        Returns a list of dicts with keys: ``title``, ``url``, ``valid_from``,
        ``valid_to``.
        """
        entries: list[dict[str, Any]] = []

        # Look for flyer cards (common patterns on Esselunga).
        card_selectors = [
            "a[href*='volantino']",
            "a[href*='flyer']",
            ".flyer-card a",
            "[data-testid*='flyer'] a",
            ".promo-card a",
        ]

        for sel in card_selectors:
            cards = page.locator(sel)
            count = await cards.count()
            if count == 0:
                continue

            for i in range(count):
                card = cards.nth(i)
                href = await card.get_attribute("href") or ""
                title = (await card.inner_text()).strip()[:200]

                # Try to extract validity dates from surrounding text.
                valid_from, valid_to = self._extract_dates(title)

                full_url = href if href.startswith("http") else f"https://www.esselunga.it{href}"
                entries.append(
                    {
                        "title": title or "Volantino Esselunga",
                        "url": full_url,
                        "valid_from": valid_from,
                        "valid_to": valid_to,
                    }
                )

            if entries:
                break

        # Deduplicate by URL.
        seen: set[str] = set()
        unique: list[dict[str, Any]] = []
        for e in entries:
            if e["url"] not in seen:
                seen.add(e["url"])
                unique.append(e)
        return unique

    # ------------------------------------------------------------------
    # Process a single flyer (open viewer, screenshot pages)
    # ------------------------------------------------------------------

    async def _process_flyer_entry(
        self, parent_page: Page, entry: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Open a flyer, screenshot all pages, run pipeline."""
        url = entry["url"]
        logger.info("Opening Esselunga flyer: %s", url)

        page = await self._new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded")
            await self._accept_cookies(page)
            await page.wait_for_timeout(3000)

            image_paths = await self._screenshot_flyer_pages(page, entry["title"])

            if not image_paths:
                logger.warning("No page screenshots captured for: %s", url)
                return None

            result = {
                "chain": self.name,
                "slug": self.slug,
                "title": entry["title"],
                "source_url": url,
                "valid_from": entry.get("valid_from") or date.today(),
                "valid_to": entry.get("valid_to") or date.today(),
                "image_paths": [str(p) for p in image_paths],
            }

            # Persist flyer and run AI pipeline.
            await self._persist_and_extract(result)
            return result

        finally:
            await page.close()

    async def _screenshot_flyer_pages(
        self, page: Page, flyer_title: str
    ) -> list[Path]:
        """Navigate through the interactive viewer and capture each page."""
        paths: list[Path] = []
        slug_title = re.sub(r"[^a-zA-Z0-9]+", "_", flyer_title)[:40].strip("_").lower()
        max_pages = 60  # safety limit

        # Wait for the flyer viewer to render.
        await page.wait_for_timeout(3000)

        for page_num in range(1, max_pages + 1):
            filename = f"{slug_title}_p{page_num:03d}.png"
            path = await self.save_screenshot(page, filename=filename, full_page=False)
            paths.append(path)

            # Attempt to go to the next page.
            advanced = await self._advance_viewer_page(page)
            if not advanced:
                logger.info(
                    "Reached last page (%d) of flyer '%s'.", page_num, flyer_title
                )
                break

        return paths

    async def _advance_viewer_page(self, page: Page) -> bool:
        """Click the 'next page' control in the flyer viewer.

        Returns ``True`` if navigation succeeded, ``False`` at the last page.
        """
        next_selectors = [
            "button[aria-label*='next' i]",
            "button[aria-label*='prossim' i]",
            "button[aria-label*='avanti' i]",
            ".next-page",
            "[data-testid='next-page']",
            "button:has-text('>')",
            "button:has-text('Avanti')",
            ".arrow-right",
            "svg.arrow-right",
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
                        # Button visible but disabled -- last page.
                        return False
            except (PlaywrightTimeout, Exception):
                continue

        # Fallback: try pressing the right arrow key.
        try:
            await page.keyboard.press("ArrowRight")
            await page.wait_for_timeout(1500)
            # We cannot be sure this actually changed the page, but assume yes
            # for now -- the caller stops when screenshots stop changing.
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Database persistence
    # ------------------------------------------------------------------

    async def _persist_and_extract(self, flyer_data: dict[str, Any]) -> None:
        """Create the Flyer row and run the extraction pipeline."""
        async with async_session() as session:
            # Resolve chain.
            from sqlalchemy import select

            stmt = select(Chain).where(Chain.slug == self.slug)
            result = await session.execute(stmt)
            chain = result.scalar_one_or_none()

            if chain is None:
                logger.error(
                    "Chain '%s' not found in DB. "
                    "Make sure seed data is loaded before scraping.",
                    self.slug,
                )
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

        # Run OCR + Gemini pipeline (uses its own DB session internally).
        await self.pipeline.process_flyer(
            flyer_id=flyer_id,
            image_paths=flyer_data["image_paths"],
            chain_name=self.name,
            chain_id=chain_id,
        )

    # ------------------------------------------------------------------
    # Date parsing helper
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_dates(text: str) -> tuple[date | None, date | None]:
        """Try to parse Italian date ranges like 'dal 10/02 al 23/02/2025'.

        Returns ``(valid_from, valid_to)`` or ``(None, None)`` on failure.
        """
        patterns = [
            # "dal 10/02/2025 al 23/02/2025"
            r"dal?\s+(\d{1,2})[/.](\d{1,2})[/.](\d{4})\s+al?\s+(\d{1,2})[/.](\d{1,2})[/.](\d{4})",
            # "dal 10/02 al 23/02/2025"
            r"dal?\s+(\d{1,2})[/.](\d{1,2})\s+al?\s+(\d{1,2})[/.](\d{1,2})[/.](\d{4})",
            # "10/02 - 23/02/2025"
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
