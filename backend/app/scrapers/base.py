"""Abstract base scraper for all supermarket chain scrapers."""

from __future__ import annotations

import hashlib
import logging
import re
from abc import ABC, abstractmethod
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import httpx
from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from app.config import get_settings

logger = logging.getLogger(__name__)

# Directory where downloaded images / screenshots are stored.
IMAGES_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "images"


class BaseScraper(ABC):
    """Base class every chain-specific scraper must extend.

    Subclasses MUST set ``name``, ``slug`` and ``base_url`` as class-level
    attributes and implement :meth:`scrape`.
    """

    # ------------------------------------------------------------------
    # Chain-specific configuration (override in subclasses)
    # ------------------------------------------------------------------
    name: str = ""
    slug: str = ""
    base_url: str = ""

    def __init__(self) -> None:
        self.settings = get_settings()
        self._playwright = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._http_client: httpx.AsyncClient | None = None

        # Ensure image storage directory exists.
        self._images_dir = IMAGES_DIR / self.slug
        self._images_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Playwright browser lifecycle
    # ------------------------------------------------------------------

    async def _launch_browser(self) -> BrowserContext:
        """Launch a Playwright Chromium browser and return a context."""
        if self._context is not None:
            return self._context

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self.settings.scraping_headless,
        )
        self._context = await self._browser.new_context(
            viewport={"width": 1920, "height": 1080},
            locale="it-IT",
            timezone_id="Europe/Rome",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            geolocation={"latitude": 45.5845, "longitude": 9.2744},
            permissions=["geolocation"],
        )
        self._context.set_default_timeout(self.settings.scraping_timeout)
        return self._context

    async def _new_page(self) -> Page:
        """Create a new browser page inside the current context."""
        ctx = await self._launch_browser()
        return await ctx.new_page()

    async def _close_browser(self) -> None:
        """Gracefully shut down the browser."""
        if self._context:
            await self._context.close()
            self._context = None
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

    # ------------------------------------------------------------------
    # HTTP client
    # ------------------------------------------------------------------

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Return a shared ``httpx.AsyncClient``."""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0),
                follow_redirects=True,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"
                    ),
                    "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
                },
            )
        return self._http_client

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @abstractmethod
    async def scrape(self) -> list[dict[str, Any]]:
        """Run the full scrape cycle for this chain.

        Returns a list of flyer-data dictionaries.  Each dictionary should
        contain at least ``title``, ``valid_from``, ``valid_to``,
        ``source_url``, ``image_paths`` (list of local file paths for each
        page image), plus any extra metadata the concrete scraper provides.
        """

    # ------------------------------------------------------------------
    # Image downloading helpers
    # ------------------------------------------------------------------

    async def download_images(self, urls: list[str]) -> list[Path]:
        """Download a list of image URLs and return local file paths."""
        client = await self._get_http_client()
        paths: list[Path] = []
        for url in urls:
            try:
                path = await self.save_image(url, client=client)
                paths.append(path)
            except Exception:
                logger.exception("Failed to download image: %s", url)
        return paths

    async def save_image(
        self,
        url: str,
        *,
        data: bytes | None = None,
        client: httpx.AsyncClient | None = None,
        filename: str | None = None,
    ) -> Path:
        """Download (or persist) a single image and return its local path.

        Parameters
        ----------
        url:
            Remote URL of the image.  Used to derive a filename when
            *filename* is not provided, and to perform the actual download
            when *data* is ``None``.
        data:
            If already fetched (e.g. a Playwright screenshot), pass the raw
            bytes directly to skip the HTTP request.
        client:
            Optional ``httpx.AsyncClient`` to reuse.
        filename:
            Explicit filename to use.  When omitted a deterministic name is
            derived from *url*.
        """
        if filename is None:
            url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
            extension = Path(url.rsplit("?", 1)[0]).suffix or ".png"
            filename = f"{url_hash}{extension}"

        dest = self._images_dir / filename
        if dest.exists():
            logger.debug("Image already cached: %s", dest)
            return dest

        if data is None:
            if client is None:
                client = await self._get_http_client()
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.content

        dest.write_bytes(data)
        logger.info("Saved image %s (%d bytes)", dest, len(data))
        return dest

    async def save_screenshot(
        self,
        page: Page,
        *,
        filename: str,
        full_page: bool = True,
    ) -> Path:
        """Take a Playwright screenshot and persist it locally."""
        dest = self._images_dir / filename
        await page.screenshot(path=str(dest), full_page=full_page)
        logger.info("Saved screenshot %s", dest)
        return dest

    # ------------------------------------------------------------------
    # Price / text normalisation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def normalize_price(raw: str | None) -> Decimal | None:
        """Parse an Italian-formatted price string into a ``Decimal``.

        Handles formats like ``"3,99"`` ``"3.99"`` ``"EUR 1.299,50"``
        ``"1,50 euro"`` etc.  Returns ``None`` when parsing fails.
        """
        if not raw:
            return None

        text = raw.strip().lower()
        # Strip known currency markers.
        for token in ("eur", "euro", "\u20ac"):
            text = text.replace(token, "")
        text = text.strip()

        if not text:
            return None

        # Determine Italian vs English format:
        # Italian: 1.299,50  --  period is thousands sep, comma is decimal.
        # English: 1,299.50  --  comma is thousands sep, period is decimal.
        # Simple heuristic: if the *last* separator is a comma, treat as Italian.
        last_comma = text.rfind(",")
        last_dot = text.rfind(".")

        if last_comma > last_dot:
            # Italian format: strip dots (thousands), replace comma -> dot.
            text = text.replace(".", "").replace(",", ".")
        elif last_dot > last_comma:
            # English format (or no comma at all): strip commas (thousands).
            text = text.replace(",", "")
        else:
            # Neither comma nor dot -- just digits.
            pass

        # Remove anything that is not digit or dot.
        text = re.sub(r"[^\d.]", "", text)

        try:
            return Decimal(text)
        except (InvalidOperation, ValueError):
            logger.debug("Could not parse price from '%s'", raw)
            return None

    @staticmethod
    def normalize_discount_pct(raw: str | None) -> Decimal | None:
        """Extract a discount percentage from strings like ``'-30%'``, ``'sconto 25%'``."""
        if not raw:
            return None
        match = re.search(r"(\d+(?:[.,]\d+)?)\s*%", raw)
        if not match:
            return None
        value = match.group(1).replace(",", ".")
        try:
            return Decimal(value)
        except (InvalidOperation, ValueError):
            return None

    # ------------------------------------------------------------------
    # Product dedup via ProductMatcher
    # ------------------------------------------------------------------

    async def _find_or_create_product(
        self,
        prod_data: dict,
        *,
        session=None,
    ):
        """Find an existing product by fuzzy match or create a new one.

        Delegates to :class:`~app.services.product_matcher.ProductMatcher`.
        ``prod_data`` must contain at least a ``name`` key.
        """
        from app.services.product_matcher import ProductMatcher

        matcher = ProductMatcher()
        return await matcher.create_or_match_product(prod_data, session=session)

    # ------------------------------------------------------------------
    # Teardown
    # ------------------------------------------------------------------

    async def close(self) -> None:
        """Release all resources (browser + HTTP client)."""
        await self._close_browser()
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()
            self._http_client = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
        return False
