"""Iperal scraper -- downloads PDF flyers, converts to images, extracts offers.

Source: https://www.iperal.it (flyer / volantino section)

Strategy:
    1. Navigate to the Iperal website and locate current flyer PDFs.
    2. Download each PDF.
    3. Convert PDF pages to images using ``pdf2image``.
    4. Feed images through the OCR + Gemini pipeline.
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import date
from pathlib import Path
from typing import Any

import httpx
from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

from app.config import get_settings
from app.database import async_session
from app.models.chain import Chain
from app.models.flyer import Flyer
from app.scrapers.base import BaseScraper
from app.scrapers.pipeline import ScrapingPipeline

logger = logging.getLogger(__name__)


class IperalScraper(BaseScraper):
    """Scraper for Iperal supermarket PDF flyers."""

    name = "Iperal"
    slug = "iperal"
    base_url = "https://www.iperal.it"

    # Known flyer landing pages to probe.
    FLYER_URLS = [
        "https://www.iperal.it/volantino",
        "https://www.iperal.it/offerte",
        "https://www.iperal.it/promozioni",
    ]

    def __init__(self) -> None:
        super().__init__()
        self.pipeline = ScrapingPipeline()
        # Subdirectory for PDFs.
        self._pdf_dir = self._images_dir / "pdfs"
        self._pdf_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def scrape(self) -> list[dict[str, Any]]:
        """Execute the full Iperal scraping workflow."""
        flyers_data: list[dict[str, Any]] = []

        try:
            page = await self._new_page()

            # Find a working flyer page.
            working_url = await self._find_working_url(page)
            if working_url is None:
                logger.error("Could not reach any Iperal flyer page.")
                return []

            await self._accept_cookies(page)
            await page.wait_for_timeout(2000)

            # Discover flyer PDFs.
            pdf_entries = await self._find_pdf_links(page)

            if not pdf_entries:
                # Fallback: look for an embedded viewer and screenshot it.
                logger.info(
                    "No PDF links found -- attempting embedded viewer fallback."
                )
                fallback = await self._fallback_viewer(page)
                if fallback:
                    flyers_data.append(fallback)
                return flyers_data

            for entry in pdf_entries:
                try:
                    flyer_data = await self._process_pdf_entry(entry)
                    if flyer_data:
                        flyers_data.append(flyer_data)
                except Exception:
                    logger.exception(
                        "Error processing Iperal PDF entry: %s", entry.get("title")
                    )

        except Exception:
            logger.exception("Iperal scraping failed.")
        finally:
            await self.close()

        return flyers_data

    # ------------------------------------------------------------------
    # URL probing
    # ------------------------------------------------------------------

    async def _find_working_url(self, page: Page) -> str | None:
        for url in self.FLYER_URLS:
            try:
                logger.info("Trying Iperal URL: %s", url)
                resp = await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                if resp and resp.ok:
                    logger.info("Iperal URL OK: %s", url)
                    return url
            except (PlaywrightTimeout, Exception):
                logger.debug("Iperal URL failed: %s", url)
                continue
        return None

    # ------------------------------------------------------------------
    # Cookie consent
    # ------------------------------------------------------------------

    async def _accept_cookies(self, page: Page) -> None:
        selectors = [
            "button#onetrust-accept-btn-handler",
            "button:has-text('Accetta tutti')",
            "button:has-text('Accetta')",
            "#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll",
            "button:has-text('OK')",
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
    # Discover PDF links
    # ------------------------------------------------------------------

    async def _find_pdf_links(self, page: Page) -> list[dict[str, Any]]:
        """Find PDF download links on the page."""
        entries: list[dict[str, Any]] = []
        seen: set[str] = set()

        # Look for direct PDF links.
        pdf_links = page.locator("a[href$='.pdf'], a[href*='.pdf?']")
        count = await pdf_links.count()
        logger.info("Found %d potential PDF links.", count)

        for i in range(count):
            link = pdf_links.nth(i)
            href = await link.get_attribute("href") or ""
            title = (await link.inner_text()).strip()[:200]

            if not href or href in seen:
                continue

            full_url = href if href.startswith("http") else f"{self.base_url}{href}"
            seen.add(full_url)

            valid_from, valid_to = self._extract_dates(title)
            entries.append(
                {
                    "title": title or "Volantino Iperal",
                    "url": full_url,
                    "valid_from": valid_from,
                    "valid_to": valid_to,
                }
            )

        # Also check for links that might lead to PDFs (download buttons, etc.).
        download_selectors = [
            "a[href*='volantino']",
            "a[href*='flyer']",
            "a:has-text('Scarica')",
            "a:has-text('Download')",
            "button:has-text('Sfoglia il volantino')",
        ]
        for sel in download_selectors:
            links = page.locator(sel)
            cnt = await links.count()
            for i in range(cnt):
                lk = links.nth(i)
                href = await lk.get_attribute("href") or ""
                if not href or href in seen or ".pdf" not in href.lower():
                    continue
                full_url = href if href.startswith("http") else f"{self.base_url}{href}"
                seen.add(full_url)
                title = (await lk.inner_text()).strip()[:200]
                valid_from, valid_to = self._extract_dates(title)
                entries.append(
                    {
                        "title": title or "Volantino Iperal",
                        "url": full_url,
                        "valid_from": valid_from,
                        "valid_to": valid_to,
                    }
                )

        return entries

    # ------------------------------------------------------------------
    # Download PDF
    # ------------------------------------------------------------------

    async def _download_pdf(self, url: str, filename: str | None = None) -> Path | None:
        """Download a PDF file and return the local path."""
        if filename is None:
            import hashlib

            url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
            filename = f"{url_hash}.pdf"

        dest = self._pdf_dir / filename
        if dest.exists():
            logger.debug("PDF already cached: %s", dest)
            return dest

        client = await self._get_http_client()
        try:
            resp = await client.get(url, follow_redirects=True, timeout=60.0)
            resp.raise_for_status()

            content_type = resp.headers.get("content-type", "")
            if "pdf" not in content_type and not resp.content[:5] == b"%PDF-":
                logger.warning(
                    "URL did not return a PDF (content-type=%s): %s",
                    content_type,
                    url,
                )
                return None

            dest.write_bytes(resp.content)
            logger.info("Downloaded PDF: %s (%d bytes)", dest, len(resp.content))
            return dest

        except httpx.HTTPStatusError as exc:
            logger.error("PDF download failed (HTTP %d): %s", exc.response.status_code, url)
            return None
        except Exception:
            logger.exception("PDF download failed: %s", url)
            return None

    # ------------------------------------------------------------------
    # PDF -> Images conversion
    # ------------------------------------------------------------------

    @staticmethod
    def _pdf_to_images(pdf_path: Path, output_dir: Path, dpi: int = 200) -> list[Path]:
        """Convert each page of a PDF into a PNG image.

        Requires ``poppler`` to be installed on the system.
        """
        try:
            from pdf2image import convert_from_path
        except ImportError:
            logger.error(
                "pdf2image is not installed. "
                "Install it with: pip install pdf2image"
            )
            return []

        image_paths: list[Path] = []
        try:
            images = convert_from_path(str(pdf_path), dpi=dpi, fmt="png")
        except Exception:
            logger.exception("Failed to convert PDF to images: %s", pdf_path)
            return []

        stem = pdf_path.stem
        for idx, img in enumerate(images, start=1):
            out_file = output_dir / f"{stem}_p{idx:03d}.png"
            img.save(str(out_file), "PNG")
            image_paths.append(out_file)
            logger.debug("Saved PDF page image: %s", out_file)

        logger.info(
            "Converted %s to %d images (dpi=%d).", pdf_path.name, len(image_paths), dpi
        )
        return image_paths

    # ------------------------------------------------------------------
    # Process a PDF flyer entry
    # ------------------------------------------------------------------

    async def _process_pdf_entry(
        self, entry: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Download PDF, convert to images, run pipeline."""
        url = entry["url"]
        logger.info("Processing Iperal PDF flyer: %s", url)

        # Download the PDF.
        slug_title = re.sub(r"[^a-zA-Z0-9]+", "_", entry["title"])[:30].strip("_").lower()
        pdf_path = await self._download_pdf(url, filename=f"{slug_title}.pdf")
        if pdf_path is None:
            return None

        # Convert to images.
        image_paths = self._pdf_to_images(pdf_path, self._images_dir)
        if not image_paths:
            logger.warning("No images generated from PDF: %s", pdf_path)
            return None

        result = {
            "chain": self.name,
            "slug": self.slug,
            "title": entry["title"],
            "source_url": url,
            "valid_from": entry.get("valid_from") or date.today(),
            "valid_to": entry.get("valid_to") or date.today(),
            "image_paths": [str(p) for p in image_paths],
            "pdf_path": str(pdf_path),
        }

        # Persist and run extraction.
        await self._persist_and_extract(result)
        return result

    # ------------------------------------------------------------------
    # Fallback: embedded viewer screenshot
    # ------------------------------------------------------------------

    async def _fallback_viewer(self, page: Page) -> dict[str, Any] | None:
        """If no PDFs found, screenshot the embedded viewer."""
        logger.info("Attempting Iperal embedded viewer fallback.")

        # Check for iframe viewer.
        iframe = page.locator(
            "iframe[src*='viewer'], iframe[src*='flyer'], iframe[src*='volantino']"
        ).first
        try:
            if await iframe.is_visible(timeout=5000):
                # Make iframe full-screen.
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
                await page.wait_for_timeout(2000)
        except (PlaywrightTimeout, Exception):
            pass

        # Take a full-page screenshot.
        path = await self.save_screenshot(page, filename="iperal_viewer_full.png", full_page=True)

        result = {
            "chain": self.name,
            "slug": self.slug,
            "title": "Volantino Iperal",
            "source_url": str(page.url),
            "valid_from": date.today(),
            "valid_to": date.today(),
            "image_paths": [str(path)],
        }
        await self._persist_and_extract(result)
        return result

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
