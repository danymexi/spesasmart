"""Iperal scraper -- extracts offers from iperal.it.

Strategy:
    1. Try scraping HTML offers directly from iperal.it (no Gemini needed).
    2. If HTML extraction succeeds, persist products directly.
    3. Fallback: locate PDF flyer links, download, convert to images, feed
       through OCR + Gemini pipeline (requires Gemini quota).
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

from app.config import get_settings
from app.database import async_session
from app.models.chain import Chain
from app.models.flyer import Flyer
from app.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class IperalScraper(BaseScraper):
    """Scraper for Iperal supermarket offers."""

    name = "Iperal"
    slug = "iperal"
    base_url = "https://www.iperal.it"

    # Pages to probe for offers
    OFFER_URLS = [
        "https://www.iperal.it/offerte",
        "https://www.iperal.it/volantino",
        "https://www.iperal.it/promozioni",
        "https://www.iperal.it/volantini",
    ]

    def __init__(self, *, store_id: uuid.UUID | None = None) -> None:
        self.store_id = store_id
        super().__init__()
        self._pdf_dir = self._images_dir / "pdfs"
        self._pdf_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def scrape(self) -> list[dict[str, Any]]:
        """Execute the Iperal scraping workflow.

        Tries HTML scraping first (no Gemini needed), falls back to
        PDF + Gemini pipeline if HTML extraction fails.
        """
        flyers_data: list[dict[str, Any]] = []

        try:
            page = await self._new_page()

            # Try each URL until one works
            working_url = await self._find_working_url(page)
            if working_url is None:
                logger.error("Could not reach any Iperal page.")
                return []

            await self._accept_cookies(page)
            await page.wait_for_timeout(2000)

            # ----- Strategy 1: HTML offers extraction (no Gemini) -----
            html_products = await self._extract_html_offers(page)
            if html_products:
                logger.info(
                    "Extracted %d products from Iperal HTML.", len(html_products)
                )
                today = date.today()
                days_since_monday = today.weekday()
                valid_from = today - timedelta(days=days_since_monday)
                valid_to = valid_from + timedelta(days=13)

                flyer_data = {
                    "chain": self.name,
                    "slug": self.slug,
                    "title": "Offerte Iperal",
                    "source_url": working_url,
                    "valid_from": valid_from,
                    "valid_to": valid_to,
                    "products": html_products,
                    "image_paths": [],
                    "store_id": self.store_id,
                }
                await self._persist_offers(flyer_data)
                flyers_data.append(flyer_data)
                return flyers_data

            # ----- Strategy 2: navigate to sub-pages for offers -----
            offer_links = await self._discover_offer_links(page)
            for link_url in offer_links:
                try:
                    sub_page = await self._new_page()
                    await sub_page.goto(link_url, wait_until="domcontentloaded", timeout=15000)
                    await self._accept_cookies(sub_page)
                    await sub_page.wait_for_timeout(2000)

                    sub_products = await self._extract_html_offers(sub_page)
                    await sub_page.close()

                    if sub_products:
                        today = date.today()
                        days_since_monday = today.weekday()
                        valid_from = today - timedelta(days=days_since_monday)
                        valid_to = valid_from + timedelta(days=13)

                        flyer_data = {
                            "chain": self.name,
                            "slug": self.slug,
                            "title": f"Offerte Iperal",
                            "source_url": link_url,
                            "valid_from": valid_from,
                            "valid_to": valid_to,
                            "products": sub_products,
                            "image_paths": [],
                            "store_id": self.store_id,
                        }
                        await self._persist_offers(flyer_data)
                        flyers_data.append(flyer_data)
                except Exception:
                    logger.exception("Error processing Iperal sub-page: %s", link_url)

            if flyers_data:
                return flyers_data

            # ----- Strategy 3: PDF + Gemini pipeline (fallback) -----
            logger.info("No HTML offers found. Trying PDF fallback.")
            pdf_entries = await self._find_pdf_links(page)
            for entry in pdf_entries:
                try:
                    flyer_data = await self._process_pdf_entry(entry)
                    if flyer_data:
                        flyers_data.append(flyer_data)
                except Exception:
                    logger.exception(
                        "Error processing Iperal PDF entry: %s", entry.get("title")
                    )

            if not flyers_data:
                # Last resort: screenshot the page
                fallback = await self._fallback_viewer(page)
                if fallback:
                    flyers_data.append(fallback)

        except Exception:
            logger.exception("Iperal scraping failed.")
        finally:
            await self.close()

        return flyers_data

    # ------------------------------------------------------------------
    # URL probing
    # ------------------------------------------------------------------

    async def _find_working_url(self, page: Page) -> str | None:
        for url in self.OFFER_URLS:
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
    # HTML offers extraction (no Gemini needed)
    # ------------------------------------------------------------------

    async def _extract_html_offers(self, page: Page) -> list[dict[str, Any]]:
        """Extract products from Iperal HTML pages.

        Looks for product cards, offer sections, or any structured product data.
        """
        # Scroll to load lazy content
        for _ in range(10):
            prev_h = await page.evaluate("document.body.scrollHeight")
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(1000)
            new_h = await page.evaluate("document.body.scrollHeight")
            if new_h == prev_h:
                break

        products = await page.evaluate("""() => {
            const results = [];
            const seen = new Set();

            // Try various card/tile selectors
            const selectors = [
                '.product-card', '.product-tile', '.offer-card',
                '[class*="product"]', '[class*="offerta"]', '[class*="promo"]',
                'article', '.card',
            ];

            let cards = [];
            for (const sel of selectors) {
                const els = document.querySelectorAll(sel);
                if (els.length > 2) {
                    cards = els;
                    break;
                }
            }

            for (const card of cards) {
                const text = card.innerText || '';
                if (text.length < 10) continue;

                // Extract name (first meaningful text)
                const titleEl = card.querySelector('h2, h3, h4, [class*="title"], [class*="name"]');
                let name = titleEl ? titleEl.innerText.trim() : '';

                if (!name) {
                    // Take first line of text
                    const lines = text.split('\\n').map(l => l.trim()).filter(l => l.length > 2);
                    if (lines.length > 0) name = lines[0];
                }

                if (!name || name.length < 2 || seen.has(name.toLowerCase())) continue;
                seen.add(name.toLowerCase());

                // Extract prices
                const priceMatches = text.match(/(\\d+[,.]\\d{2})\\s*€/g);
                let offerPrice = null;
                let originalPrice = null;
                if (priceMatches && priceMatches.length > 0) {
                    offerPrice = priceMatches[0].replace('€', '').trim();
                    if (priceMatches.length > 1) {
                        originalPrice = priceMatches[1].replace('€', '').trim();
                    }
                }

                // Discount
                let discount = null;
                const discountMatch = text.match(/-\\s*(\\d+)\\s*%/);
                if (discountMatch) discount = discountMatch[1];

                // Image
                const imgEl = card.querySelector('img');
                const imgSrc = imgEl ? (imgEl.src || imgEl.getAttribute('data-src')) : null;

                // Quantity
                let quantity = null;
                const qtyMatch = text.match(/(\\d+(?:[,.]\\d+)?\\s*(?:g|kg|ml|l|cl|pz|pezzi|conf)\\b)/i);
                if (qtyMatch) quantity = qtyMatch[1];

                results.push({
                    name: name,
                    offer_price: offerPrice,
                    original_price: originalPrice,
                    discount_pct: discount,
                    quantity: quantity,
                    image_url: imgSrc,
                    raw_text: text.substring(0, 400),
                });
            }
            return results;
        }""")

        parsed: list[dict[str, Any]] = []
        for item in products:
            name = (item.get("name") or "").strip()
            if not name:
                continue

            offer_price = self.normalize_price(item.get("offer_price"))
            if offer_price is None:
                continue

            original_price = self.normalize_price(item.get("original_price"))
            if original_price and original_price < offer_price:
                original_price, offer_price = offer_price, original_price

            discount_pct = None
            if item.get("discount_pct"):
                try:
                    discount_pct = Decimal(item["discount_pct"])
                except Exception:
                    pass

            parsed.append({
                "name": name,
                "brand": None,
                "category": None,
                "original_price": str(original_price) if original_price else None,
                "offer_price": str(offer_price),
                "discount_pct": str(discount_pct) if discount_pct else None,
                "discount_type": "percentage" if discount_pct else None,
                "quantity": item.get("quantity"),
                "price_per_unit": None,
                "raw_text": item.get("raw_text", ""),
                "confidence": 0.75,
                "image_url": item.get("image_url"),
            })

        return parsed

    # ------------------------------------------------------------------
    # Discover offer sub-page links
    # ------------------------------------------------------------------

    async def _discover_offer_links(self, page: Page) -> list[str]:
        """Find links to offer sub-pages on the current page."""
        seen: set[str] = set()
        urls: list[str] = []

        link_selectors = [
            "a[href*='offert']",
            "a[href*='promo']",
            "a[href*='volantino']",
            "a[href*='risparm']",
        ]

        for sel in link_selectors:
            links = page.locator(sel)
            count = await links.count()
            for i in range(count):
                try:
                    href = await links.nth(i).get_attribute("href") or ""
                    if not href or href == "#":
                        continue
                    full_url = href if href.startswith("http") else f"{self.base_url}{href}"
                    if full_url not in seen and full_url != str(page.url):
                        seen.add(full_url)
                        urls.append(full_url)
                except Exception:
                    continue

        return urls[:10]  # Limit to 10 sub-pages

    # ------------------------------------------------------------------
    # PDF link discovery
    # ------------------------------------------------------------------

    async def _find_pdf_links(self, page: Page) -> list[dict[str, Any]]:
        """Find PDF download links on the page."""
        entries: list[dict[str, Any]] = []
        seen: set[str] = set()

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
            entries.append({
                "title": title or "Volantino Iperal",
                "url": full_url,
                "valid_from": valid_from,
                "valid_to": valid_to,
            })

        # Also check for download buttons
        download_selectors = [
            "a[href*='volantino']",
            "a:has-text('Scarica')",
            "a:has-text('Download')",
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
                entries.append({
                    "title": title or "Volantino Iperal",
                    "url": full_url,
                    "valid_from": valid_from,
                    "valid_to": valid_to,
                })

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
                    content_type, url,
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
        """Convert each page of a PDF into a PNG image."""
        try:
            from pdf2image import convert_from_path
        except ImportError:
            logger.error("pdf2image is not installed.")
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

        logger.info("Converted %s to %d images.", pdf_path.name, len(image_paths))
        return image_paths

    # ------------------------------------------------------------------
    # Process a PDF flyer entry
    # ------------------------------------------------------------------

    async def _process_pdf_entry(self, entry: dict[str, Any]) -> dict[str, Any] | None:
        """Download PDF, convert to images, run Gemini pipeline."""
        url = entry["url"]
        logger.info("Processing Iperal PDF flyer: %s", url)

        slug_title = re.sub(r"[^a-zA-Z0-9]+", "_", entry["title"])[:30].strip("_").lower()
        pdf_path = await self._download_pdf(url, filename=f"{slug_title}.pdf")
        if pdf_path is None:
            return None

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

        await self._persist_and_extract(result)
        return result

    # ------------------------------------------------------------------
    # Fallback: embedded viewer screenshot
    # ------------------------------------------------------------------

    async def _fallback_viewer(self, page: Page) -> dict[str, Any] | None:
        """If no PDFs or HTML offers found, screenshot the page."""
        logger.info("Attempting Iperal fallback screenshot.")

        iframe = page.locator(
            "iframe[src*='viewer'], iframe[src*='flyer'], iframe[src*='volantino']"
        ).first
        try:
            if await iframe.is_visible(timeout=5000):
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
    # Database persistence -- HTML offers (no Gemini)
    # ------------------------------------------------------------------

    async def _persist_offers(self, flyer_data: dict[str, Any]) -> None:
        """Persist HTML-extracted offers (same pattern as PromoQui/Lidl)."""
        from app.models.offer import Offer
        from sqlalchemy import select, and_

        store_id = flyer_data.get("store_id") or self.store_id
        valid_from = flyer_data.get("valid_from") or date.today()
        valid_to = flyer_data.get("valid_to") or date.today()

        async with async_session() as session:
            stmt = select(Chain).where(Chain.slug == self.slug)
            result = await session.execute(stmt)
            chain = result.scalar_one_or_none()
            if chain is None:
                logger.error("Chain '%s' not found in DB.", self.slug)
                return

            # Date-based dedup
            stmt_existing = select(Flyer).where(
                and_(
                    Flyer.source_url == flyer_data["source_url"],
                    Flyer.chain_id == chain.id,
                    Flyer.valid_from == valid_from,
                    Flyer.valid_to == valid_to,
                )
            )
            existing = (await session.execute(stmt_existing)).scalar_one_or_none()
            if existing:
                logger.info("Iperal flyer already exists (id=%s), skipping.", existing.id)
                return

            flyer = Flyer(
                chain_id=chain.id,
                store_id=store_id,
                title=flyer_data["title"],
                valid_from=valid_from,
                valid_to=valid_to,
                source_url=flyer_data["source_url"],
                pages_count=1,
                status="processing",
            )
            session.add(flyer)
            await session.commit()
            await session.refresh(flyer)
            flyer_id = flyer.id
            chain_id = chain.id

        saved = 0
        async with async_session() as session:
            for prod_data in flyer_data.get("products", []):
                try:
                    name = (prod_data.get("name") or "").strip()
                    if not name:
                        continue

                    offer_price = self.normalize_price(prod_data.get("offer_price"))
                    if offer_price is None:
                        continue

                    brand = (prod_data.get("brand") or "").strip() or None

                    # Find or create product (fuzzy dedup via ProductMatcher)
                    product = await self._find_or_create_product(
                        {
                            "name": name,
                            "brand": brand,
                            "category": prod_data.get("category"),
                            "unit": prod_data.get("quantity"),
                            "image_url": prod_data.get("image_url"),
                        },
                        session=session,
                    )

                    discount_pct = self.normalize_discount_pct(prod_data.get("discount_pct"))
                    original_price = self.normalize_price(prod_data.get("original_price"))

                    offer = Offer(
                        product_id=product.id,
                        flyer_id=flyer_id,
                        chain_id=chain_id,
                        store_id=store_id,
                        original_price=original_price,
                        offer_price=offer_price,
                        discount_pct=discount_pct,
                        discount_type=prod_data.get("discount_type"),
                        quantity=prod_data.get("quantity"),
                        price_per_unit=None,
                        valid_from=valid_from,
                        valid_to=valid_to,
                        raw_text=prod_data.get("raw_text", "")[:500],
                        confidence=Decimal(str(prod_data.get("confidence", 0.75))),
                    )
                    session.add(offer)
                    saved += 1
                except Exception:
                    logger.exception("Failed to save Iperal product: %s", prod_data.get("name"))

            flyer = await session.get(Flyer, flyer_id)
            if flyer:
                flyer.status = "processed"
            await session.commit()

        logger.info("Iperal: persisted %d products (flyer %s).", saved, flyer_id)

    # ------------------------------------------------------------------
    # Database persistence -- PDF/Gemini pipeline
    # ------------------------------------------------------------------

    async def _persist_and_extract(self, flyer_data: dict[str, Any]) -> None:
        """Create Flyer row and run Gemini extraction pipeline."""
        from sqlalchemy import select

        async with async_session() as session:
            stmt = select(Chain).where(Chain.slug == self.slug)
            result = await session.execute(stmt)
            chain = result.scalar_one_or_none()

            if chain is None:
                logger.error("Chain '%s' not found in DB.", self.slug)
                return

            flyer = Flyer(
                chain_id=chain.id,
                store_id=self.store_id,
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

        try:
            from app.scrapers.pipeline import ScrapingPipeline
            pipeline = ScrapingPipeline()
            await pipeline.process_flyer(
                flyer_id=flyer_id,
                image_paths=flyer_data["image_paths"],
                chain_name=self.name,
                chain_id=chain_id,
                store_id=self.store_id,
            )
        except Exception:
            logger.exception("Gemini pipeline failed for Iperal flyer %s", flyer_id)

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
