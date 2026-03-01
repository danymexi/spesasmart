"""Esselunga Spesa Online catalog scraper.

Uses the Esselunga e-commerce REST API at spesaonline.esselunga.it to fetch
the product catalog.  No authentication is required — the site supports
anonymous "free visit" mode.

The API is session-based (JSESSIONID) and requires that the session be
established via the AngularJS SPA.  We use Playwright to load the SPA,
then make API calls from within the browser context via JavaScript fetch().

API endpoints used:
    GET  /commerce/resources/nav/supermercato           → full category tree (828 KB)
    POST /commerce/resources/search/facet               → product search with pagination
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from app.database import async_session
from app.services.product_matcher import ProductMatcher

logger = logging.getLogger(__name__)

SITE_URL = "https://spesaonline.esselunga.it"
BASE_URL = f"{SITE_URL}/commerce/resources"
PAGE_SIZE = 50
REQUEST_DELAY = 0.5  # seconds between batches

# ID of the "SUPERMERCATO" root node whose children are the real categories
SUPERMERCATO_ID = 300000001003363


class EsselungaOnlineScraper:
    """Scrapes the Esselunga Spesa Online product catalog via Playwright + REST."""

    def __init__(self) -> None:
        self._matcher = ProductMatcher()
        self._page = None
        self._browser = None
        self._playwright = None

    async def _init_browser(self) -> bool:
        """Launch Playwright, load the Esselunga SPA to establish a session."""
        try:
            from playwright.async_api import async_playwright

            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(headless=True)
            context = await self._browser.new_context(
                viewport={"width": 1280, "height": 720},
                locale="it-IT",
                timezone_id="Europe/Rome",
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
            )
            context.set_default_timeout(30000)
            self._page = await context.new_page()

            # Load the store home page — this initialises the Angular app
            # and establishes the JSESSIONID session
            logger.info("Esselunga: loading SPA to establish session...")
            try:
                await self._page.goto(
                    f"{SITE_URL}/commerce/nav/supermercato/store/home",
                    wait_until="networkidle",
                    timeout=60000,
                )
            except Exception:
                # networkidle can sometimes timeout — that's okay
                pass
            await self._page.wait_for_timeout(5000)

            # Accept cookies if banner appears
            try:
                btn = self._page.locator("button:has-text('Accetta tutti')").first
                if await btn.is_visible(timeout=3000):
                    await btn.click()
                    await self._page.wait_for_timeout(1000)
            except Exception:
                pass

            # Wait for Angular to be fully loaded
            angular_ready = await self._page.evaluate("""() => {
                return !!(window.angular && window.angular.element);
            }""")
            logger.info("Esselunga: Angular ready=%s", angular_ready)

            # Verify session works with a test API call
            test = await self._page.evaluate(f"""async () => {{
                try {{
                    const resp = await fetch("{BASE_URL}/nav/supermercato", {{
                        headers: {{ "Accept": "application/json" }},
                        credentials: "include",
                    }});
                    return {{ ok: resp.ok, status: resp.status }};
                }} catch (e) {{
                    return {{ error: e.message }};
                }}
            }}""")
            logger.info("Esselunga: session test=%s", test)

            if not test or not test.get("ok"):
                logger.error("Esselunga: session test failed.")
                return False

            logger.info("Esselunga: SPA loaded, session established.")
            return True

        except Exception:
            logger.exception("Failed to init Esselunga browser session.")
            return False

    async def close(self) -> None:
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

    # ------------------------------------------------------------------
    # JS-based API calls (run inside the page context)
    # ------------------------------------------------------------------

    async def _js_fetch_json(self, url: str, body: dict | None = None) -> dict | None:
        """Make an API call from within the Playwright page context.

        Uses Angular's $http service when available (includes X-PAGE-PATH
        header automatically), falls back to native fetch with manual headers.
        """
        if body is not None:
            body_json = json.dumps(body)
            result = await self._page.evaluate(f"""async () => {{
                try {{
                    // Try Angular $http first (includes X-PAGE-PATH)
                    if (window.angular) {{
                        const injector = window.angular.element(document.body).injector();
                        if (injector) {{
                            const $http = injector.get("$http");
                            if ($http) {{
                                return await new Promise((resolve, reject) => {{
                                    $http.post("{url}", {body_json}).then(
                                        resp => resolve(resp.data),
                                        err => resolve({{ __error: true, status: err.status, body: JSON.stringify(err.data) }})
                                    );
                                }});
                            }}
                        }}
                    }}
                    // Fallback to fetch with manual X-PAGE-PATH
                    const pagePath = window.location.hash
                        ? window.location.hash.replace("#!", "").split("?")[0]
                        : "/supermercato/store/home";
                    const resp = await fetch("{url}", {{
                        method: "POST",
                        headers: {{
                            "Accept": "application/json",
                            "Content-Type": "application/json",
                            "X-PAGE-PATH": pagePath,
                        }},
                        credentials: "include",
                        body: {json.dumps(body_json)},
                    }});
                    if (!resp.ok) return {{ __error: true, status: resp.status, body: await resp.text() }};
                    return await resp.json();
                }} catch (e) {{
                    return {{ __error: true, message: e.message }};
                }}
            }}""")
        else:
            result = await self._page.evaluate(f"""async () => {{
                try {{
                    // Try Angular $http first
                    if (window.angular) {{
                        const injector = window.angular.element(document.body).injector();
                        if (injector) {{
                            const $http = injector.get("$http");
                            if ($http) {{
                                return await new Promise((resolve, reject) => {{
                                    $http.get("{url}").then(
                                        resp => resolve(resp.data),
                                        err => resolve({{ __error: true, status: err.status, body: JSON.stringify(err.data) }})
                                    );
                                }});
                            }}
                        }}
                    }}
                    // Fallback to fetch
                    const pagePath = window.location.hash
                        ? window.location.hash.replace("#!", "").split("?")[0]
                        : "/supermercato/store/home";
                    const resp = await fetch("{url}", {{
                        headers: {{
                            "Accept": "application/json",
                            "X-PAGE-PATH": pagePath,
                        }},
                        credentials: "include",
                    }});
                    if (!resp.ok) return {{ __error: true, status: resp.status, body: await resp.text() }};
                    return await resp.json();
                }} catch (e) {{
                    return {{ __error: true, message: e.message }};
                }}
            }}""")

        if result and result.get("__error"):
            logger.warning("Esselunga API error: %s", str(result)[:200])
            return None
        return result

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def scrape(self) -> int:
        """Scrape all products from Esselunga Spesa Online.

        Returns the total number of products processed.
        """
        total = 0
        try:
            if not await self._init_browser():
                logger.error("Could not establish Esselunga browser session.")
                return 0

            # Build category lookup from the nav tree
            cat_lookup = await self._build_category_lookup()
            logger.info(
                "Esselunga Online: built category lookup with %d product-set mappings.",
                len(cat_lookup),
            )

            # Scrape ALL products via a single paginated search.
            # The search/facet API does not filter by categoryId reliably,
            # so we fetch everything and assign categories from the nav tree.
            total = await self._scrape_all_products(cat_lookup)

        except Exception:
            logger.exception("Esselunga Online catalog scrape failed.")
        finally:
            await self.close()

        logger.info("Esselunga Online catalog scrape complete: %d products.", total)
        return total

    # ------------------------------------------------------------------
    # Category lookup from nav tree
    # ------------------------------------------------------------------

    async def _build_category_lookup(self) -> dict[str, tuple[str, str]]:
        """Build a product-code → (category, subcategory) lookup from the nav tree.

        Each menu item has ``menuItemProductSets`` containing ``productSetIds``.
        We build a reverse map from productSetId → category so that when we
        scrape all products, we can assign the correct category.

        Returns dict mapping productSetId (str) → (parentLabel, childLabel).
        """
        data = await self._js_fetch_json(f"{BASE_URL}/nav/supermercato")
        if not data:
            return {}

        items = data.get("leftMenuItems", [])
        if not items:
            return {}

        # Build lookup maps
        id_to_item: dict[int, dict] = {}
        id_to_label: dict[int, str] = {}
        id_to_parent: dict[int, int | None] = {}
        id_to_children: dict[int, list[int]] = {}

        for item in items:
            item_id = item.get("id")
            if not item_id:
                continue
            label = (item.get("label") or "").strip()
            parent_id = item.get("parentMenuItemId")
            id_to_item[item_id] = item
            id_to_label[item_id] = label
            id_to_parent[item_id] = parent_id
            if parent_id:
                id_to_children.setdefault(parent_id, []).append(item_id)

        # Get the children of SUPERMERCATO — the 26 top-level grocery categories
        superm_children = id_to_children.get(SUPERMERCATO_ID, [])
        if not superm_children:
            logger.warning("No children found for SUPERMERCATO node.")
            return {}

        # Map productSetId → (parent_category, sub_category)
        pset_to_cat: dict[str, tuple[str, str]] = {}

        for child_id in superm_children:
            child_label = id_to_label.get(child_id, "")
            if not child_label:
                continue

            grandchildren = id_to_children.get(child_id, [])
            if grandchildren:
                for gc_id in grandchildren:
                    gc_label = id_to_label.get(gc_id, "")
                    if not gc_label:
                        continue
                    gc_item = id_to_item.get(gc_id, {})
                    for ps in gc_item.get("menuItemProductSets", []):
                        for ps_id in ps.get("productSetIds", []):
                            pset_to_cat[str(ps_id)] = (child_label, gc_label)
            else:
                child_item = id_to_item.get(child_id, {})
                for ps in child_item.get("menuItemProductSets", []):
                    for ps_id in ps.get("productSetIds", []):
                        pset_to_cat[str(ps_id)] = (child_label, child_label)

        logger.info(
            "Esselunga: %d top-level categories, %d product-set mappings.",
            len(superm_children),
            len(pset_to_cat),
        )
        return pset_to_cat

    # ------------------------------------------------------------------
    # Product scraping
    # ------------------------------------------------------------------

    async def _scrape_all_products(
        self, cat_lookup: dict[str, tuple[str, str]]
    ) -> int:
        """Paginate through ALL products using search/facet (no category filter).

        Assigns categories from the nav tree's product-set mappings.
        """
        saved = 0
        start = 0
        logged_sample = False

        while True:
            body = {
                "query": "*",
                "start": start,
                "length": PAGE_SIZE,
                "filters": [],
            }

            data = await self._js_fetch_json(f"{BASE_URL}/search/facet", body)
            if not data:
                break

            # Products are in displayables.entities
            displayables = data.get("displayables", data)
            products = displayables.get("entities", [])
            row_count = displayables.get("rowCount", 0)

            if not products:
                break

            # Log sample product structure on first batch
            if not logged_sample and products:
                sample = products[0]
                logger.info(
                    "Esselunga: sample product keys=%s",
                    list(sample.keys())[:20],
                )
                # Check for category-related fields
                for key in ("productSets", "categorizedProduct", "category",
                            "categoryId", "menuItemId", "productSetId"):
                    if key in sample:
                        val = sample[key]
                        logger.info("Esselunga: product.%s = %s", key, str(val)[:200])
                logged_sample = True

            async with async_session() as session:
                for prod in products:
                    try:
                        # Determine category from product-set mappings
                        cat, subcat = self._resolve_category(prod, cat_lookup)
                        count = await self._save_product(
                            prod, subcat, cat, session
                        )
                        saved += count
                    except Exception:
                        logger.exception(
                            "Failed to save Esselunga product: %s",
                            prod.get("description"),
                        )

            start += len(products)

            if start % 500 == 0:
                logger.info(
                    "Esselunga Online: %d/%d products processed (%d saved).",
                    start, row_count or "?", saved,
                )

            # Check pagination end
            if row_count and start >= row_count:
                break
            if len(products) < PAGE_SIZE:
                break

            await asyncio.sleep(REQUEST_DELAY)

        return saved

    @staticmethod
    def _resolve_category(
        prod: dict[str, Any],
        cat_lookup: dict[str, tuple[str, str]],
    ) -> tuple[str, str]:
        """Resolve product category from nav-tree product-set mapping.

        Falls back to a generic "Supermercato" category if no mapping is found.
        """
        # Check if product has productSets or similar fields
        product_sets = prod.get("productSets") or []
        if isinstance(product_sets, list):
            for ps_id in product_sets:
                cat_info = cat_lookup.get(str(ps_id))
                if cat_info:
                    return cat_info

        # Try categorizedProduct field
        cat_prod = prod.get("categorizedProduct") or {}
        if isinstance(cat_prod, dict):
            cat_name = (cat_prod.get("category") or "").strip()
            if cat_name:
                return (cat_name, cat_name)

        return ("Supermercato", "Supermercato")

    # ------------------------------------------------------------------
    # Product persistence
    # ------------------------------------------------------------------

    async def _save_product(
        self,
        prod: dict[str, Any],
        category_name: str,
        parent_name: str,
        session,
    ) -> int:
        """Save a single product via ProductMatcher. Returns 1 on success, 0 on skip."""
        description = (prod.get("description") or "").strip()
        if not description or len(description) < 2:
            return 0

        # Brand
        brand = (prod.get("brand") or "").strip() or None
        if brand and brand.lower() == "unbranded":
            brand = None

        # Image URL (prefer big size)
        image_url = (prod.get("imageURL") or "").strip() or None
        images = prod.get("images") or []
        if images:
            for img in images:
                big = (img.get("big") or "").strip()
                if big:
                    image_url = big
                    break

        # Unit — extract from description
        unit = self._extract_unit(description, prod.get("label"))
        if unit and len(unit) > 50:
            unit = unit[:47] + "..."

        # Product code (Esselunga internal code, not a real barcode/EAN)
        code = (prod.get("code") or "").strip() or None

        # Use parent category name as main category
        category = parent_name or category_name

        await self._matcher.create_or_match_product(
            {
                "name": description,
                "brand": brand,
                "category": category,
                "subcategory": category_name if category_name != parent_name else None,
                "unit": unit,
                "barcode": code,
                "image_url": image_url,
                "source": "esselunga_online",
            },
            session=session,
        )
        return 1

    @staticmethod
    def _extract_unit(description: str, label: str | None = None) -> str | None:
        """Extract a short unit string from the product description.

        The description often ends with a quantity like:
            "Burro formato contadino 250 g"
            "Latte intero 1 l"
            "Pasta Barilla fusilli 500 g"
        """
        if not description:
            return None

        # Match patterns like "250 g", "1 l", "500 ml", "1,5 kg", "6 x 1,5 l"
        qty_match = re.search(
            r"(\d+(?:[.,]\d+)?\s*(?:x\s*\d+(?:[.,]\d+)?\s*)?"
            r"(?:g|kg|ml|cl|l|pz|pezzi|conf|capsule|bustine|rotoli|fette|compresse))\b",
            description,
            re.IGNORECASE,
        )
        if qty_match:
            return qty_match.group(1).strip()

        # Try "Nxweight" patterns like "6x1,5 l"
        multi_match = re.search(
            r"(\d+\s*x\s*\d+(?:[.,]\d+)?\s*"
            r"(?:g|kg|ml|cl|l))\b",
            description,
            re.IGNORECASE,
        )
        if multi_match:
            return multi_match.group(1).strip()

        return None
