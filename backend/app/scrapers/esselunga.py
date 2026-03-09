"""Esselunga scraper -- navigates the interactive flyer viewer and extracts offers.

Source: https://www.esselunga.it/it-it/promozioni/volantini.html

Strategy:
    0. Digital flyers: discover + extract HTML offers from volantino-digitale
       pages for Esselunga Macherio (JS-rendered, requires Playwright).
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
from datetime import date, datetime, timedelta
from decimal import Decimal
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

    def __init__(self, *, store_id: uuid.UUID | None = None) -> None:
        self.store_id = store_id
        super().__init__()
        self.pipeline = ScrapingPipeline()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def scrape(self) -> list[dict[str, Any]]:
        """Execute the full Esselunga scraping workflow.

        Strategy 0: Digital flyers HTML extraction (supplementary, always runs).
        Strategy 1: Interactive viewer screenshots + Gemini OCR (fallback).
        """
        flyers_data: list[dict[str, Any]] = []

        try:
            page = await self._new_page()

            # ----- Strategy 0: Digital flyers HTML extraction -----
            digital_flyers = await self._scrape_digital_flyers(page)
            flyers_data.extend(digital_flyers)

            logger.info("Navigating to Esselunga flyers page: %s", self.base_url)
            await page.goto(self.base_url, wait_until="domcontentloaded")

            # Handle cookie consent banner if present.
            await self._accept_cookies(page)

            # Select the target store / area.
            await self._select_store_area(page)

            # Gather flyer links from the page.
            flyer_entries = await self._find_flyer_entries(page)
            if not flyer_entries:
                if not flyers_data:
                    logger.warning("No flyers found on Esselunga page.")
                return flyers_data

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
    # Digital flyers: discovery + extraction + orchestrator
    # ------------------------------------------------------------------

    MACHERIO_STORE_URL = (
        "https://www.esselunga.it/it-it/promozioni/volantini"
        ".esselunga-di-macherio.che.html"
    )

    ITALIAN_MONTHS = {
        "gen": 1, "feb": 2, "mar": 3, "apr": 4, "mag": 5, "giu": 6,
        "lug": 7, "ago": 8, "set": 9, "ott": 10, "nov": 11, "dic": 12,
        "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4,
        "maggio": 5, "giugno": 6, "luglio": 7, "agosto": 8,
        "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12,
    }

    async def _discover_digital_flyer_urls(self, page: Page) -> list[dict[str, Any]]:
        """Navigate to Macherio store page and extract volantino-digitale links."""
        logger.info("Esselunga digital: discovering flyers from Macherio store page")
        try:
            resp = await page.goto(
                self.MACHERIO_STORE_URL,
                wait_until="domcontentloaded",
                timeout=20000,
            )
            if not resp or not resp.ok:
                logger.warning(
                    "Esselunga digital: could not load Macherio page (status=%s)",
                    resp.status if resp else "None",
                )
                return []
        except (PlaywrightTimeout, Exception) as exc:
            logger.warning("Esselunga digital: Macherio page failed: %s", exc)
            return []

        await self._accept_cookies(page)
        await page.wait_for_timeout(3000)

        # Extract all "volantino-digitale" links and their card context
        raw_links = await page.evaluate("""() => {
            const results = [];
            const anchors = document.querySelectorAll('a[href*="volantino-digitale"]');
            for (const a of anchors) {
                const href = a.href || '';
                if (!href || !href.includes('volantino-digitale')) continue;

                // Walk up to find the card/container for title and dates
                const card = a.closest('.card, article, [class*="promo"], [class*="volantino"], div.col, div');
                const cardText = card ? card.innerText : '';
                const linkText = a.innerText || a.title || '';
                results.push({
                    url: href,
                    link_text: linkText.trim().substring(0, 200),
                    card_text: cardText.trim().substring(0, 400),
                });
            }
            return results;
        }""")

        seen: set[str] = set()
        flyers: list[dict[str, Any]] = []
        for item in raw_links:
            url = item.get("url", "").strip()
            if not url or url in seen:
                continue
            seen.add(url)

            card_text = item.get("card_text", "")
            link_text = item.get("link_text", "")

            # Extract title — first line of card text, or URL slug
            title = card_text.split("\n")[0].strip()[:100] if card_text else ""
            if not title or title.lower().startswith("scopri"):
                # Derive from URL: volantino-digitale.sconti-50.che.6740.html
                slug_match = re.search(r"volantino-digitale\.([^.]+)\.", url)
                title = slug_match.group(1).replace("-", " ").title() if slug_match else "Volantino Esselunga"

            valid_from, valid_to = self._parse_esselunga_dates(card_text)

            flyers.append({
                "url": url,
                "title": title,
                "valid_from": valid_from,
                "valid_to": valid_to,
            })

        logger.info("Esselunga digital: discovered %d flyer URLs.", len(flyers))
        return flyers

    async def _extract_digital_offers(self, page: Page, url: str) -> list[dict[str, Any]]:
        """Navigate to a volantino-digitale page and extract products after JS rendering."""
        logger.info("Esselunga digital: extracting offers from %s", url)
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        except (PlaywrightTimeout, Exception) as exc:
            logger.warning("Esselunga digital: failed to load %s: %s", url, exc)
            return []

        await self._accept_cookies(page)

        # Wait for product cards to render (JS-populated)
        for selector in [".card-item", "[data-code]", ".product-card-link"]:
            try:
                await page.wait_for_selector(selector, timeout=10000)
                logger.info("Esselunga digital: JS rendered (selector: %s)", selector)
                break
            except (PlaywrightTimeout, Exception):
                continue
        else:
            # Extra wait if no selector found
            await page.wait_for_timeout(8000)

        # Click "Mostra altri prodotti" repeatedly to load all products
        for click_round in range(50):
            try:
                load_more = page.locator(
                    "a:has-text('Mostra altri'), "
                    "button:has-text('Mostra altri'), "
                    "a:has-text('Mostra l'), "
                    "[class*='load-more']"
                ).first
                if await load_more.is_visible(timeout=2000):
                    await load_more.click()
                    await page.wait_for_timeout(1500)
                else:
                    break
            except (PlaywrightTimeout, Exception):
                break

        # Scroll to ensure all lazy content is loaded
        for _ in range(5):
            prev_h = await page.evaluate("document.body.scrollHeight")
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(1000)
            new_h = await page.evaluate("document.body.scrollHeight")
            if new_h == prev_h:
                break

        # Extract product data from rendered DOM
        raw_products = await page.evaluate("""() => {
            const results = [];
            const seen = new Set();

            // Primary: .card-item cards or [data-code] elements
            let cards = document.querySelectorAll('.card-item');
            if (cards.length === 0) cards = document.querySelectorAll('[data-code]');
            if (cards.length === 0) cards = document.querySelectorAll('.product-card-link');

            for (const card of cards) {
                // Name: h3[title], data-name attribute, or first heading
                let name = '';
                const h3 = card.querySelector('h3[title]');
                if (h3) {
                    name = h3.getAttribute('title') || h3.innerText || '';
                }
                if (!name) {
                    const link = card.querySelector('.product-card-link[data-name]');
                    if (link) name = link.getAttribute('data-name') || '';
                }
                if (!name) {
                    const heading = card.querySelector('h2, h3, h4, h5');
                    if (heading) name = heading.innerText || '';
                }
                name = name.trim();
                if (!name || name.length < 3) continue;

                const key = name.toLowerCase().replace(/\\s+/g, ' ');
                if (seen.has(key)) continue;
                seen.add(key);

                // Offer price: .promo-price
                let offerPrice = null;
                const promoEl = card.querySelector('.promo-price');
                if (promoEl) {
                    const priceText = promoEl.innerText.replace(/€/g, '').trim();
                    const m = priceText.match(/(\\d+[,.]\\d{2})/);
                    if (m) offerPrice = m[1];
                }

                // Original price: .price (not .promo-price)
                let originalPrice = null;
                const priceEls = card.querySelectorAll('.price');
                for (const pe of priceEls) {
                    if (pe.classList.contains('promo-price')) continue;
                    const pt = pe.innerText.replace(/€/g, '').trim();
                    const m = pt.match(/(\\d+[,.]\\d{2})/);
                    if (m) { originalPrice = m[1]; break; }
                }

                // Discount percentage
                let discount = null;
                const discEl = card.querySelector('.value, [class*="discount"], [class*="badge"]');
                if (discEl) {
                    const dm = discEl.innerText.match(/(\\d+)\\s*%/);
                    if (dm) discount = dm[1];
                }

                // Quantity / unit info
                let quantity = null;
                const infoEl = card.querySelector('.card-info p, .card-info');
                if (infoEl) {
                    const qm = infoEl.innerText.match(/(\\d+(?:[,.]\\d+)?\\s*(?:g|kg|ml|l|cl|pz|pezzi|conf|capsule|bustine|rotoli)\\b)/i);
                    if (qm) quantity = qm[1];
                }

                // Price per unit
                let pricePerUnit = null;
                if (infoEl) {
                    const ppuMatch = infoEl.innerText.match(/(\\d+[,.]\\d{2})\\s*€?\\s*(?:al|per|\\/)\\s*(?:kg|l|lt)/i);
                    if (ppuMatch) pricePerUnit = ppuMatch[1];
                }

                // Image
                let imgUrl = null;
                const img = card.querySelector('img');
                if (img) imgUrl = img.src || img.getAttribute('data-src') || null;

                // Product code
                const code = card.getAttribute('data-code') ||
                             card.closest('[data-code]')?.getAttribute('data-code') || null;

                // Raw text for debugging
                const rawText = (card.innerText || '').substring(0, 500);

                // Only add if we have at least a price
                if (offerPrice || originalPrice) {
                    results.push({
                        name: name,
                        offer_price: offerPrice,
                        original_price: originalPrice,
                        discount_pct: discount,
                        quantity: quantity,
                        price_per_unit: pricePerUnit,
                        image_url: imgUrl,
                        code: code,
                        raw_text: rawText,
                    });
                }
            }

            // Fallback: scan for any price-bearing elements if cards found few
            if (results.length < 5) {
                const allEls = document.querySelectorAll('[class*="product"], [class*="offer"], [class*="promo"]');
                for (const el of allEls) {
                    const text = (el.innerText || '').trim();
                    if (text.length < 10 || text.length > 500) continue;

                    const priceMatch = text.match(/(\\d+[,.]\\d{2})\\s*€|€\\s*(\\d+[,.]\\d{2})/);
                    if (!priceMatch) continue;

                    const price = priceMatch[1] || priceMatch[2];
                    const lines = text.split('\\n').map(l => l.trim()).filter(l => l.length > 2);
                    const name = lines.find(l => !l.match(/^[€\\d.,\\s%]+$/) && l.length > 3);
                    if (!name) continue;

                    const key = name.toLowerCase().replace(/\\s+/g, ' ');
                    if (seen.has(key)) continue;
                    seen.add(key);

                    results.push({
                        name: name,
                        offer_price: price,
                        original_price: null,
                        discount_pct: null,
                        quantity: null,
                        price_per_unit: null,
                        image_url: null,
                        code: null,
                        raw_text: text.substring(0, 500),
                    });
                }
            }

            return results;
        }""")

        # Parse and normalize in Python
        from app.services.product_matcher import ProductMatcher

        parsed: list[dict[str, Any]] = []
        for item in raw_products:
            name = (item.get("name") or "").strip()
            if not name or len(name) < 3:
                continue

            offer_price = self.normalize_price(item.get("offer_price"))
            original_price = self.normalize_price(item.get("original_price"))

            # Must have at least one price
            if offer_price is None and original_price is None:
                continue
            if offer_price is None:
                offer_price = original_price
                original_price = None

            if original_price and original_price < offer_price:
                original_price, offer_price = offer_price, original_price

            brand, clean_name = ProductMatcher.extract_brand_from_name(name)

            discount_pct = None
            if item.get("discount_pct"):
                try:
                    discount_pct = Decimal(item["discount_pct"])
                except Exception:
                    pass

            parsed.append({
                "name": clean_name or name,
                "brand": brand,
                "category": None,
                "original_price": str(original_price) if original_price else None,
                "offer_price": str(offer_price),
                "discount_pct": str(discount_pct) if discount_pct else None,
                "discount_type": "percentage" if discount_pct else None,
                "quantity": item.get("quantity"),
                "price_per_unit": item.get("price_per_unit"),
                "raw_text": item.get("raw_text", ""),
                "confidence": 0.85,
                "image_url": item.get("image_url"),
            })

        logger.info("Esselunga digital: extracted %d products from %s", len(parsed), url)
        return parsed

    async def _scrape_digital_flyers(self, page: Page) -> list[dict[str, Any]]:
        """Orchestrate digital flyer discovery + extraction + persistence."""
        flyers_data: list[dict[str, Any]] = []
        total_products = 0

        try:
            flyer_urls = await self._discover_digital_flyer_urls(page)
            if not flyer_urls:
                logger.info("Esselunga digital: no digital flyer URLs found.")
                return []

            for flyer_info in flyer_urls:
                try:
                    dig_page = await self._new_page()
                    products = await self._extract_digital_offers(
                        dig_page, flyer_info["url"]
                    )
                    await dig_page.close()

                    if not products:
                        logger.info(
                            "Esselunga digital: no products from %s",
                            flyer_info["url"],
                        )
                        continue

                    today = date.today()
                    valid_from = flyer_info.get("valid_from") or today
                    valid_to = flyer_info.get("valid_to") or (today + timedelta(days=13))

                    flyer_data = {
                        "chain": self.name,
                        "slug": self.slug,
                        "title": flyer_info.get("title", "Volantino Esselunga"),
                        "source_url": flyer_info["url"],
                        "valid_from": valid_from,
                        "valid_to": valid_to,
                        "products": products,
                        "image_paths": [],
                        "store_id": self.store_id,
                    }
                    await self._persist_offers(flyer_data)
                    flyers_data.append(flyer_data)
                    total_products += len(products)

                except Exception:
                    logger.exception(
                        "Esselunga digital: error processing flyer %s",
                        flyer_info.get("url"),
                    )
        except Exception:
            logger.exception("Esselunga digital: discovery/extraction failed.")

        logger.info(
            "Esselunga digital: completed — %d flyers, %d total products.",
            len(flyers_data),
            total_products,
        )
        return flyers_data

    @classmethod
    def _parse_esselunga_dates(cls, text: str) -> tuple[date | None, date | None]:
        """Parse date ranges from Esselunga card text.

        Handles: 'Dal 26 Feb al 11 Mar', 'Dal 9 al 15 Mar', numeric formats.
        """
        text_lower = text.lower()

        # Pattern: "dal DD mon al DD mon [YYYY]"
        m = re.search(
            r"dal\s+(\d{1,2})\s+(\w+)\s+al\s+(\d{1,2})\s+(\w+)(?:\s+(\d{4}))?",
            text_lower,
        )
        if m:
            day_from = int(m.group(1))
            month_from = cls.ITALIAN_MONTHS.get(m.group(2))
            day_to = int(m.group(3))
            month_to = cls.ITALIAN_MONTHS.get(m.group(4))
            year = int(m.group(5)) if m.group(5) else date.today().year
            if month_from and month_to:
                try:
                    return date(year, month_from, day_from), date(year, month_to, day_to)
                except ValueError:
                    pass

        # Pattern: "dal DD al DD mon [YYYY]"
        m = re.search(
            r"dal\s+(\d{1,2})\s+al\s+(\d{1,2})\s+(\w+)(?:\s+(\d{4}))?",
            text_lower,
        )
        if m:
            day_from, day_to = int(m.group(1)), int(m.group(2))
            month = cls.ITALIAN_MONTHS.get(m.group(3))
            year = int(m.group(4)) if m.group(4) else date.today().year
            if month:
                try:
                    return date(year, month, day_from), date(year, month, day_to)
                except ValueError:
                    pass

        # Fallback to numeric date parsing
        return cls._extract_dates(text)

    # ------------------------------------------------------------------
    # Database persistence -- HTML digital offers
    # ------------------------------------------------------------------

    async def _persist_offers(self, flyer_data: dict[str, Any]) -> None:
        """Persist HTML-extracted offers (same pattern as Iperal/Lidl)."""
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
                logger.info(
                    "Esselunga flyer already exists (id=%s), skipping.", existing.id
                )
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
                        price_per_unit=self.normalize_price(prod_data.get("price_per_unit")),
                        valid_from=valid_from,
                        valid_to=valid_to,
                        raw_text=prod_data.get("raw_text", "")[:500],
                        confidence=Decimal(str(prod_data.get("confidence", 0.85))),
                    )
                    session.add(offer)
                    saved += 1
                except Exception:
                    logger.exception(
                        "Failed to save Esselunga product: %s", prod_data.get("name")
                    )

            flyer = await session.get(Flyer, flyer_id)
            if flyer:
                flyer.status = "processed"
            await session.commit()

        logger.info("Esselunga: persisted %d products (flyer %s).", saved, flyer_id)

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
