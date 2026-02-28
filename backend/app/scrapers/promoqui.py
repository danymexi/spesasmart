"""PromoQui aggregator scraper -- extracts offers from promoqui.it.

This scraper serves as an alternative data source when direct chain scraping
(Gemini OCR) is unavailable. PromoQui aggregates flyer offers from Italian
supermarkets in structured HTML format.

Supported chains: esselunga, coop, iperal, lidl
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

from app.database import async_session
from app.models.chain import Chain
from app.models.flyer import Flyer
from app.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

# Map our chain slugs to PromoQui URL slugs
PROMOQUI_CHAINS = {
    "esselunga": "esselunga",
    "coop": "coop",
    "iperal": "iperal",
    "lidl": "lidl",
}


class PromoQuiScraper(BaseScraper):
    """Scraper that pulls offers from promoqui.it for a given chain."""

    name = "PromoQui"
    slug = "promoqui"
    base_url = "https://www.promoqui.it"

    def __init__(self, chain_slug: str, *, store_id: uuid.UUID | None = None) -> None:
        self.chain_slug = chain_slug
        self.chain_name = chain_slug.title()
        self.store_id = store_id
        # Override name/slug to match the actual chain
        self.name = self.chain_name
        self.slug = chain_slug
        super().__init__()

    async def _new_page_plain(self) -> Page:
        """Create a plain browser page without locale/UA that triggers geo-lock.

        PromoQui geo-localizes based on locale/UA headers and shows only
        local offers (e.g. 4 items in Milan).  A clean context without
        these headers shows the full national catalog (e.g. 282 items).
        """
        from playwright.async_api import async_playwright as ap

        if self._context is None:
            self._playwright = await ap().start()
            self._browser = await self._playwright.chromium.launch(
                headless=self.settings.scraping_headless
            )
            self._context = await self._browser.new_context(
                viewport={"width": 1920, "height": 1080},
            )
            self._context.set_default_timeout(self.settings.scraping_timeout)
        return await self._context.new_page()

    async def scrape(self) -> list[dict[str, Any]]:
        """Scrape offers for the configured chain from PromoQui."""
        pq_slug = PROMOQUI_CHAINS.get(self.chain_slug)
        if not pq_slug:
            logger.error("Chain '%s' not supported on PromoQui.", self.chain_slug)
            return []

        url = f"{self.base_url}/offerte/{pq_slug}"
        flyers_data: list[dict[str, Any]] = []

        try:
            page = await self._new_page_plain()
            logger.info("Navigating to PromoQui: %s", url)
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await self._accept_cookies(page)
            await page.wait_for_timeout(2000)

            # Load ALL offers by clicking "CARICA ALTRE OFFERTE" up to 50 times
            await self._load_all_offers(page)

            # Extract products
            products = await self._extract_offers(page)

            if not products:
                logger.info("No offers found for '%s' on PromoQui.", self.chain_slug)
                return []

            # NO food filter -- load EVERYTHING into the catalog
            logger.info(
                "Extracted %d total products for '%s' from PromoQui.",
                len(products),
                self.chain_slug,
            )

            today = date.today()
            days_since_monday = today.weekday()
            valid_from = today - timedelta(days=days_since_monday)
            valid_to = valid_from + timedelta(days=13)  # 2 weeks typical

            flyer_data = {
                "chain": self.chain_name,
                "slug": self.chain_slug,
                "title": f"Offerte {self.chain_name} (PromoQui)",
                "source_url": url,
                "valid_from": valid_from,
                "valid_to": valid_to,
                "products": products,
                "image_paths": [],
                "store_id": self.store_id,
            }

            await self._persist_offers(flyer_data)
            flyers_data.append(flyer_data)

        except Exception:
            logger.exception("PromoQui scraping failed for '%s'.", self.chain_slug)
        finally:
            await self.close()

        return flyers_data

    # ------------------------------------------------------------------
    # Cookie consent
    # ------------------------------------------------------------------

    async def _accept_cookies(self, page: Page) -> None:
        """Dismiss cookie consent dialogs (multiple possible providers)."""
        # Try clicking via JS to handle overlays that block Playwright clicks
        dismissed = await page.evaluate("""() => {
            // Common consent button texts
            const texts = ['ACCETTO', 'Accetta', 'Accetta tutti', 'Accept', 'Accept All'];
            const btns = document.querySelectorAll('button, a[role="button"], [class*="consent"] button');
            for (const b of btns) {
                const t = b.innerText.trim();
                for (const target of texts) {
                    if (t === target || t.toUpperCase() === target.toUpperCase()) {
                        b.click();
                        return true;
                    }
                }
            }
            // Also check for iframes (e.g. Didomi, OneTrust)
            return false;
        }""")
        if dismissed:
            await page.wait_for_timeout(1000)
            return

        # Fallback: Playwright selectors
        selectors = [
            "button:has-text('ACCETTO')",
            "button:has-text('Accetta')",
            "button#onetrust-accept-btn-handler",
            "button:has-text('Accetta tutti')",
            "button:has-text('Accept')",
        ]
        for sel in selectors:
            try:
                btn = page.locator(sel).first
                if await btn.is_visible(timeout=2000):
                    await btn.click()
                    await page.wait_for_timeout(500)
                    return
            except (PlaywrightTimeout, Exception):
                continue

    # ------------------------------------------------------------------
    # Set location to Monza area
    # ------------------------------------------------------------------

    async def _set_location(self, page: Page) -> None:
        """Set PromoQui location to Monza e Brianza for local offers."""
        # PromoQui has a location search input. We type "Monza" and select.
        try:
            # Look for the location/city input field
            set_ok = await page.evaluate("""() => {
                // Find the search/location input by placeholder or nearby text
                const inputs = document.querySelectorAll('input');
                for (const inp of inputs) {
                    const ph = (inp.placeholder || '').toLowerCase();
                    if (ph.includes('cerca') || ph.includes('città') || ph.includes('dove') || ph.includes('localit')) {
                        inp.value = '';
                        inp.focus();
                        return 'found_input';
                    }
                }
                // Check for a "TROVAMI" or location button
                const btns = document.querySelectorAll('button, a');
                for (const b of btns) {
                    const text = b.innerText.trim().toUpperCase();
                    if (text.includes('MONZA') || text.includes('TROVAMI')) {
                        return 'found_btn:' + b.innerText.trim();
                    }
                }
                return 'not_found';
            }""")
            logger.info("Location search result: %s", set_ok)

            if set_ok == "found_input":
                # Type Monza in the input
                inputs = page.locator("input")
                for i in range(await inputs.count()):
                    inp = inputs.nth(i)
                    ph = await inp.get_attribute("placeholder") or ""
                    if any(k in ph.lower() for k in ("cerca", "città", "dove", "localit")):
                        await inp.fill("Monza")
                        await page.wait_for_timeout(1500)
                        # Click the first suggestion
                        await page.evaluate("""() => {
                            const items = document.querySelectorAll('[class*="suggestion"], [class*="autocomplete"] li, [class*="result"] a');
                            for (const item of items) {
                                if (item.innerText.toLowerCase().includes('monza')) {
                                    item.click();
                                    return true;
                                }
                            }
                            return false;
                        }""")
                        await page.wait_for_timeout(2000)
                        break

        except Exception:
            logger.warning("Could not set PromoQui location to Monza.")

    # ------------------------------------------------------------------
    # Load all offers (scroll + "load more" button) -- up to 50 rounds
    # ------------------------------------------------------------------

    async def _load_all_offers(self, page: Page, max_loads: int = 50) -> None:
        """Scroll and click 'load more' repeatedly to get ALL offers.

        PromoQui loads ~50 offer cards per batch.  We count only direct offer
        cards (``OffersList_offer__`` that are NOT sub-elements like image/info).
        """
        # Count only direct offer card divs, excluding sub-elements.
        CARD_COUNTER_JS = """(() => {
            const all = document.querySelectorAll('[class*="OffersList_offer__"]');
            return [...all].filter(el => {
                const cls = el.className;
                return !cls.includes('image') && !cls.includes('information') &&
                       !cls.includes('description') && !cls.includes('title') &&
                       !cls.includes('offerItem') && !cls.includes('mobilePrice') &&
                       !cls.includes('infosRetailer') && !cls.includes('buttonIcon');
            }).length;
        })()"""
        consecutive_no_new = 0
        prev_count = await page.evaluate(CARD_COUNTER_JS)
        logger.info("Initial offer cards visible: %d", prev_count)

        for i in range(max_loads):
            # Scroll to bottom to trigger lazy loading
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(1000)

            # Click "CARICA ALTRE OFFERTE" via JavaScript.
            # PromoQui uses React; Playwright's click() doesn't always trigger
            # the React event handler, but native JS .click() does.
            # Match exactly "CARICA ALTRE OFFERTE" to avoid clicking unrelated buttons.
            clicked = await page.evaluate("""() => {
                const btns = document.querySelectorAll('button');
                for (const b of btns) {
                    const text = b.innerText.trim().toUpperCase();
                    if (text === 'CARICA ALTRE OFFERTE' && b.offsetParent !== null && b.offsetHeight > 0) {
                        b.scrollIntoView({behavior: 'instant', block: 'center'});
                        b.click();
                        return true;
                    }
                }
                return false;
            }""")
            if clicked:
                await page.wait_for_timeout(3000)

            # Count offer cards now
            current_count = await page.evaluate(CARD_COUNTER_JS)

            if current_count > prev_count:
                consecutive_no_new = 0
                logger.info(
                    "Load round %d: %d -> %d offer cards.", i + 1, prev_count, current_count
                )
            else:
                consecutive_no_new += 1

            prev_count = current_count

            # Stop if no new content for 3 consecutive rounds
            if not clicked and consecutive_no_new >= 3:
                logger.info(
                    "No more offers to load after %d rounds (%d cards).",
                    i + 1,
                    current_count,
                )
                break

        logger.info(
            "Finished loading: %d rounds, %d offer cards.",
            min(i + 1, max_loads),
            prev_count,
        )

    # ------------------------------------------------------------------
    # Extract offers from HTML
    # ------------------------------------------------------------------

    async def _extract_offers(self, page: Page) -> list[dict[str, Any]]:
        """Extract structured offer data from PromoQui offer cards.

        PromoQui DOM structure (as of Feb 2026):
            div.OffersList_offer__vyBiG          <- individual offer card
              div.OffersList_offer__image__*      <- image wrapper
                a[href="/volantino/..."]          <- link to flyer page
                  img[src, alt, title]            <- product image + name
              div.OffersList_offer__information__* <- info wrapper
                div.*description*                 <- product name
                div (hidden-sm)                   <- "VOLANTINO XX.XX€ Chain"
                div (hidden-md-up)                <- "Chain XX.XX€"
        """
        products: list[dict[str, Any]] = []

        offers_data = await page.evaluate("""() => {
            // Select individual offer cards (filter out sub-elements).
            // PromoQui renders each card twice (mobile + desktop).
            // We deduplicate by name+price inside the JS to avoid doubles.
            const allOfferEls = document.querySelectorAll('[class*="OffersList_offer__"]');
            const offerCards = [...allOfferEls].filter(el => {
                const cls = el.className;
                return cls.includes('OffersList_offer__') &&
                       !cls.includes('image') &&
                       !cls.includes('information') &&
                       !cls.includes('description') &&
                       !cls.includes('title') &&
                       !cls.includes('offerItem') &&
                       !cls.includes('mobilePrice') &&
                       !cls.includes('infosRetailer') &&
                       !cls.includes('buttonIcon');
            });

            const results = [];
            const seen = new Set();

            for (const el of offerCards) {
                const imgEl = el.querySelector('img');
                const descEl = el.querySelector('[class*="description"]');
                const titleEl = el.querySelector('[class*="title"]');

                let name = '';
                if (descEl) name = descEl.innerText.trim();
                if (!name && titleEl) name = titleEl.innerText.trim();
                if (!name && imgEl) name = (imgEl.alt || imgEl.title || '').trim();
                if (!name || name.length < 2) continue;

                const text = el.innerText || '';

                // Price: XX.XX€ or XX,XX€ (€ may be on next line)
                let offerPrice = null;
                let originalPrice = null;
                const priceMatches = text.match(/(\\d+[,.]\\d{2})\\s*€/g);
                if (priceMatches && priceMatches.length > 0) {
                    offerPrice = priceMatches[0].replace('€', '').trim();
                    if (priceMatches.length > 1) {
                        originalPrice = priceMatches[1].replace('€', '').trim();
                    }
                }

                // JS-level dedup: same name+price = same product (mobile/desktop)
                const dedupKey = name.toLowerCase().substring(0, 60) + '|' + (offerPrice || '');
                if (seen.has(dedupKey)) continue;
                seen.add(dedupKey);

                let discount = null;
                const discountMatch = text.match(/-\\s*(\\d+)\\s*%/);
                if (discountMatch) discount = discountMatch[1];

                const imgSrc = imgEl ? (imgEl.src || imgEl.getAttribute('data-src')) : null;

                let quantity = null;
                const qtyMatch = text.match(/(\\d+(?:[,.]\\d+)?\\s*(?:g|kg|ml|l|cl|pz|pezzi|conf)\\b)/i);
                if (qtyMatch) quantity = qtyMatch[1];

                const linkEl = el.querySelector('a[href*="/volantino/"]');
                const href = linkEl ? linkEl.href : null;

                results.push({
                    name: name,
                    brand: null,
                    category: null,
                    offer_price: offerPrice,
                    original_price: originalPrice,
                    discount_pct: discount,
                    quantity: quantity,
                    image_url: imgSrc,
                    raw_text: text.substring(0, 500),
                    source_link: href,
                });
            }
            return results;
        }""")

        seen_products: set[str] = set()

        for item in offers_data:
            name = item.get("name", "").strip()
            if not name or len(name) < 2:
                continue

            raw_price = item.get("offer_price")
            offer_price = self.normalize_price(raw_price)
            if offer_price is None:
                continue

            # Deduplicate by name + price
            dedup_key = f"{name.lower()}|{offer_price}"
            if dedup_key in seen_products:
                continue
            seen_products.add(dedup_key)

            discount_pct = None
            if item.get("discount_pct"):
                try:
                    discount_pct = Decimal(item["discount_pct"])
                except Exception:
                    pass

            original_price = self.normalize_price(item.get("original_price"))
            # If original < offer, swap (parsing artifact)
            if original_price is not None and original_price < offer_price:
                original_price, offer_price = offer_price, original_price

            products.append({
                "name": name,
                "brand": (item.get("brand") or "").strip() or None,
                "category": (item.get("category") or "").strip() or None,
                "original_price": str(original_price) if original_price else None,
                "offer_price": str(offer_price),
                "discount_pct": str(discount_pct) if discount_pct else None,
                "discount_type": "percentage" if discount_pct else None,
                "quantity": item.get("quantity"),
                "price_per_unit": None,
                "raw_text": item.get("raw_text", ""),
                "confidence": 0.80,
                "image_url": item.get("image_url"),
            })

        return products

    # ------------------------------------------------------------------
    # Database persistence
    # ------------------------------------------------------------------

    async def _persist_offers(self, flyer_data: dict[str, Any]) -> None:
        """Create Flyer and save products to DB.

        Uses date-based deduplication: same source_url + overlapping date
        range won't create a duplicate flyer. But a new week's scraping
        creates a new flyer with new offers, building price history.
        """
        from app.models.offer import Offer
        from sqlalchemy import select, and_

        store_id = flyer_data.get("store_id")
        valid_from = flyer_data.get("valid_from") or date.today()
        valid_to = flyer_data.get("valid_to") or date.today()

        async with async_session() as session:
            # Find the chain
            stmt = select(Chain).where(Chain.slug == self.chain_slug)
            result = await session.execute(stmt)
            chain = result.scalar_one_or_none()

            if chain is None:
                logger.error("Chain '%s' not found in DB.", self.chain_slug)
                return

            # Date-based dedup: check for existing flyer with same source and
            # overlapping validity dates
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
                    "PromoQui flyer already exists for '%s' (%s to %s, id=%s), skipping.",
                    self.chain_slug,
                    valid_from,
                    valid_to,
                    existing.id,
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

        # Save products
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
                            "source": "promoqui",
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
                        valid_from=flyer_data.get("valid_from"),
                        valid_to=flyer_data.get("valid_to"),
                        raw_text=prod_data.get("raw_text", "")[:500],
                        confidence=Decimal(str(prod_data.get("confidence", 0.8))),
                    )
                    session.add(offer)
                    saved += 1

                except Exception:
                    logger.exception("Failed to save product: %s", prod_data.get("name"))

            flyer = await session.get(Flyer, flyer_id)
            if flyer:
                flyer.status = "processed"

            await session.commit()

        logger.info(
            "PromoQui: persisted %d products for '%s' (flyer %s).",
            saved,
            self.chain_slug,
            flyer_id,
        )
