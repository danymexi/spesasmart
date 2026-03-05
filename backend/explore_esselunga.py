"""Explore Esselunga API - Phase 3: POST requests and leftMenuItems deep dive."""

import asyncio
import json
from playwright.async_api import async_playwright

ESSELUNGA_URL = "https://spesaonline.esselunga.it/"


async def main():
    api_calls = []

    async def on_response(response):
        url = response.url
        content_type = response.headers.get("content-type", "")
        status = response.status

        if any(skip in url for skip in [
            ".js", ".css", ".png", ".jpg", ".jpeg", ".gif", ".svg",
            ".woff", ".woff2", ".ttf", ".ico", ".map",
            "google", "facebook", "doubleclick", "hotjar",
            "fontawesome", "fonts.googleapis", "tiktok",
            "sentry", "clarity", "criteo", "creativecdn",
            "adnxs", "rtbh",
        ]):
            return

        if "json" in content_type and "esselunga" in url:
            try:
                body = await response.text()
                body_len = len(body)
            except Exception:
                body = ""
                body_len = 0

            # Capture request details
            request = response.request
            entry = {
                "url": url,
                "method": request.method,
                "status": status,
                "content_type": content_type,
                "body_length": body_len,
                "preview": body[:3000],
            }
            # Try to get request body for POST
            try:
                post_data = request.post_data
                if post_data:
                    entry["request_body"] = post_data[:2000]
            except Exception:
                pass

            api_calls.append(entry)
            print(f"\n{'='*80}")
            print(f"[{request.method}] {status} {url}")
            print(f"Size: {body_len} | Type: {content_type}")
            if entry.get("request_body"):
                print(f"Request body: {entry['request_body'][:500]}")
            print(f"Response: {body[:400]}")

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

    # ========================================
    # STEP 1: Load site
    # ========================================
    print("\n>>> STEP 1: Loading site...")
    try:
        await page.goto(ESSELUNGA_URL, wait_until="networkidle", timeout=60000)
    except Exception:
        pass
    await page.wait_for_timeout(3000)
    await page.screenshot(path="/tmp/esselunga_01_landing.png", full_page=False)

    # Accept cookies
    try:
        btn = page.locator("button:has-text('Accetta tutti')").first
        if await btn.is_visible(timeout=3000):
            await btn.click()
            await page.wait_for_timeout(1000)
    except Exception:
        pass

    # ========================================
    # STEP 2: Get leftMenuItems from nav (full category tree)
    # ========================================
    print("\n\n>>> STEP 2: Getting FULL category tree from leftMenuItems...")

    cat_result = await page.evaluate("""async () => {
        try {
            const resp = await fetch("https://spesaonline.esselunga.it/commerce/resources/nav/supermercato", {
                headers: {'Accept': 'application/json'},
                credentials: 'include',
            });
            const data = await resp.json();

            // Get all keys from the nav response
            const result = {
                topKeys: Object.keys(data),
                powerGuest: data.powerGuest,
                freeVisit: data.freeVisit,
                hideProductPrice: data.hideProductPrice,
                searchEnabled: data.searchEnabled,
                navigation: data.navigation,
                store: data.store,
                companyCode: data.companyCode,
            };

            // leftMenuItems - main category tree
            if (data.leftMenuItems) {
                result.leftMenuItemsCount = data.leftMenuItems.length;
                result.leftMenuItems = data.leftMenuItems.map(item => ({
                    id: item.id,
                    label: item.label,
                    leaf: item.leaf,
                    isRoot: item.isRoot,
                    rootCategory: item.rootCategory,
                    showInMenu: item.showInMenu,
                    showInFilters: item.showInFilters,
                    childCount: item.menuItems?.length || 0,
                    allKeys: Object.keys(item),
                }));
            }

            // leftMenuItemsHierarchy
            if (data.leftMenuItemsHierarchy) {
                result.leftMenuItemsHierarchyCount = data.leftMenuItemsHierarchy.length;
                result.leftMenuItemsHierarchy = data.leftMenuItemsHierarchy.map(item => ({
                    id: item.id,
                    label: item.label,
                    leaf: item.leaf,
                    childCount: item.menuItems?.length || 0,
                    children: item.menuItems?.slice(0, 5).map(c => ({
                        id: c.id,
                        label: c.label,
                        leaf: c.leaf,
                        childCount: c.menuItems?.length || 0,
                    })),
                }));
            }

            // navBarMenuItems
            result.navBarMenuItems = data.navBarMenuItems?.map(item => ({
                id: item.id,
                label: item.label,
            }));

            // bottomMenuItems
            if (data.bottomMenuItems) {
                result.bottomMenuItemsCount = data.bottomMenuItems.length;
                result.bottomMenuItems = data.bottomMenuItems.map(item => ({
                    id: item.id,
                    label: item.label,
                }));
            }

            // deliveryMethods
            result.deliveryMethods = data.deliveryMethods;

            return result;
        } catch (e) {
            return { error: e.message };
        }
    }""")
    print(f">>> Nav data: {json.dumps(cat_result, indent=2, ensure_ascii=False)}")

    # ========================================
    # STEP 3: Test POST requests for search/products
    # ========================================
    print("\n\n>>> STEP 3: Testing POST requests...")

    post_endpoints = [
        {
            "url": "https://spesaonline.esselunga.it/commerce/resources/search/personalizzazioni",
            "body": "{}",
        },
        {
            "url": "https://spesaonline.esselunga.it/commerce/resources/search/personalizzazioni/menu-item",
            "body": "{}",
        },
        {
            "url": "https://spesaonline.esselunga.it/commerce/resources/search/supermercato",
            "body": '{"query":"latte"}',
        },
        {
            "url": "https://spesaonline.esselunga.it/commerce/resources/search/supermercato",
            "body": '{"query":"latte","page":0,"pageSize":20}',
        },
    ]

    for ep in post_endpoints:
        url = ep["url"]
        body = ep["body"]
        result = await page.evaluate(f"""async () => {{
            try {{
                const resp = await fetch("{url}", {{
                    method: 'POST',
                    headers: {{
                        'Accept': 'application/json',
                        'Content-Type': 'application/json',
                    }},
                    credentials: 'include',
                    body: '{body}',
                }});
                const text = await resp.text();
                return {{
                    status: resp.status,
                    bodyLength: text.length,
                    contentType: resp.headers.get('content-type'),
                    body: text.substring(0, 3000),
                }};
            }} catch (e) {{
                return {{ error: e.message }};
            }}
        }}""")
        print(f"\n  POST {url}")
        print(f"  Body: {body}")
        print(f"  -> Status: {result.get('status', '?')}, Size: {result.get('bodyLength', 0)}")
        print(f"  -> Response: {result.get('body', '')[:500]}")

    # ========================================
    # STEP 4: Interact with the site via UI to intercept actual API calls
    # ========================================
    print("\n\n>>> STEP 4: Using the actual site UI to capture real API calls...")

    # Navigate to the store home
    print("\n>>> Navigating to store home...")
    try:
        await page.goto("https://spesaonline.esselunga.it/commerce/nav/supermercato/store/home",
                        wait_until="domcontentloaded", timeout=30000)
    except Exception:
        pass
    await page.wait_for_timeout(5000)

    # Try clicking on a category in the left menu
    print("\n>>> Looking for category links in the sidebar...")
    cat_links = await page.evaluate("""() => {
        // Look for left menu / sidebar navigation elements
        const allLinks = Array.from(document.querySelectorAll('a'));
        const catLinks = allLinks.filter(a => {
            const text = a.textContent?.trim();
            const href = a.href || '';
            return (text && text.length > 2 && text.length < 50 &&
                    (href.includes('/category/') || href.includes('/categori') ||
                     href.includes('/reparto/') || href.includes('/shelf/')));
        }).map(a => ({
            text: a.textContent.trim(),
            href: a.href,
            classes: a.className?.substring(0, 80),
        }));
        return catLinks.slice(0, 20);
    }""")
    print(f">>> Category links found: {json.dumps(cat_links, indent=2, ensure_ascii=False)}")

    # Also check for Angular directives / custom elements
    print("\n>>> Checking for Angular app structure...")
    angular_info = await page.evaluate("""() => {
        const result = {};

        // Check for AngularJS
        if (window.angular) {
            result.angularVersion = window.angular.version?.full;
            const injector = window.angular.element(document.body).injector();
            if (injector) {
                result.hasInjector = true;
            }
        }

        // Check for ng-app
        const ngApp = document.querySelector('[ng-app]');
        if (ngApp) {
            result.ngAppName = ngApp.getAttribute('ng-app');
        }

        // Check for custom elements / directives
        const allElements = document.querySelectorAll('*');
        const customTags = new Set();
        for (const el of allElements) {
            if (el.tagName.includes('-') || el.tagName.startsWith('EL-')) {
                customTags.add(el.tagName.toLowerCase());
            }
        }
        result.customElements = Array.from(customTags).slice(0, 50);

        // Check for Angular scope data on leftmenu elements
        const leftMenu = document.querySelector('[class*="left-menu"], [class*="sidebar"], [el-left-menu]');
        if (leftMenu) {
            result.leftMenuTag = leftMenu.tagName;
            result.leftMenuClasses = leftMenu.className;
        }

        return result;
    }""")
    print(f">>> Angular info: {json.dumps(angular_info, indent=2, ensure_ascii=False)}")

    # ========================================
    # STEP 5: Use the search box via UI
    # ========================================
    print("\n\n>>> STEP 5: Using search UI to trigger real search API calls...")

    # First clear existing api_calls to focus on search
    search_api_calls_start = len(api_calls)

    # Find and use search box
    search_selectors = [
        "input[type='search']",
        "input[placeholder*='cerca' i]",
        "input[placeholder*='search' i]",
        "input[placeholder*='prodott' i]",
        "input[placeholder*='marc' i]",
        "[class*='search'] input",
        "[class*='Search'] input",
        "input[name='q']",
        "input[name='query']",
        "input[role='searchbox']",
        "input[aria-label*='cerca' i]",
    ]

    search_found = False
    for sel in search_selectors:
        try:
            el = page.locator(sel).first
            if await el.is_visible(timeout=3000):
                print(f">>> Found search: {sel}")
                # Get the search input details
                details = await el.evaluate("""el => ({
                    type: el.type,
                    name: el.name,
                    id: el.id,
                    placeholder: el.placeholder,
                    className: el.className,
                    ariaLabel: el.getAttribute('aria-label'),
                })""")
                print(f"    Details: {json.dumps(details)}")

                await el.click()
                await page.wait_for_timeout(500)
                await el.fill("latte")
                await page.wait_for_timeout(2000)
                await page.screenshot(path="/tmp/esselunga_05_search_typing.png", full_page=False)

                # Check for autocomplete dropdown
                autocomplete = await page.evaluate("""() => {
                    const dropdowns = document.querySelectorAll('[class*="autocompl"], [class*="suggest"], [class*="dropdown"], [class*="typeahead"], [role="listbox"]');
                    return Array.from(dropdowns).map(d => ({
                        tag: d.tagName,
                        classes: d.className?.substring(0, 100),
                        text: d.textContent?.substring(0, 300),
                        visible: d.offsetParent !== null,
                    }));
                }""")
                print(f">>> Autocomplete dropdowns: {json.dumps(autocomplete, indent=2, ensure_ascii=False)[:500]}")

                # Submit search
                await page.keyboard.press("Enter")
                await page.wait_for_timeout(6000)
                await page.screenshot(path="/tmp/esselunga_05_search_results.png", full_page=False)
                print(f">>> Search URL: {page.url}")
                search_found = True
                break
        except Exception as e:
            print(f"    Error with {sel}: {str(e)[:80]}")

    # ========================================
    # STEP 6: Try to navigate to a category via the Angular app
    # ========================================
    print("\n\n>>> STEP 6: Navigating to a category via Angular app...")

    # Click on a visible category in the left menu
    cat_clicked = False
    cat_selectors = [
        "el-left-menu a",
        ".left-menu a",
        "[class*='leftMenu'] a",
        "[class*='left-menu'] a",
        "[class*='category'] a",
        "[class*='sidebar'] a",
        "nav.sidebar a",
        "[class*='menu-item'] a",
        "li[class*='menu'] > a",
    ]

    for sel in cat_selectors:
        try:
            links = page.locator(sel)
            count = await links.count()
            if count > 2:
                print(f">>> Found {count} category links with: {sel}")
                for i in range(min(count, 10)):
                    text = (await links.nth(i).inner_text()).strip()
                    href = await links.nth(i).get_attribute("href") or ""
                    print(f"    [{i}] {text[:60]} -> {href[:100]}")

                # Click the first meaningful one
                for i in range(min(count, 10)):
                    text = (await links.nth(i).inner_text()).strip()
                    if text and len(text) > 2 and len(text) < 50:
                        print(f"\n>>> Clicking category: {text}")
                        await links.nth(i).click()
                        cat_clicked = True
                        await page.wait_for_timeout(5000)
                        await page.screenshot(path="/tmp/esselunga_06_category.png", full_page=False)
                        print(f">>> Category URL: {page.url}")
                        break
                if cat_clicked:
                    break
        except Exception as e:
            continue

    if not cat_clicked:
        # Try clicking visible text elements that look like categories
        print("\n>>> Trying to find categories in the page content...")
        all_visible_text = await page.evaluate("""() => {
            const elements = document.querySelectorAll('a, button, [role="button"], [class*="item"]');
            return Array.from(elements).filter(el => el.offsetParent !== null).map(el => ({
                tag: el.tagName,
                text: el.textContent?.trim().substring(0, 60),
                href: el.href || el.getAttribute('href') || '',
                classes: el.className?.substring(0, 80),
            })).filter(el => el.text && el.text.length > 2 && el.text.length < 50).slice(0, 40);
        }""")
        print(f">>> Visible clickable elements: {json.dumps(all_visible_text, indent=2, ensure_ascii=False)[:2000]}")

    # ========================================
    # STEP 7: Check if search/category APIs need specific headers or CSRF tokens
    # ========================================
    print("\n\n>>> STEP 7: Checking for CSRF tokens and special headers...")

    csrf_info = await page.evaluate("""() => {
        const result = {};

        // Check meta tags for CSRF
        const metas = document.querySelectorAll('meta[name*="csrf"], meta[name*="token"], meta[name*="_token"]');
        result.csrfMetas = Array.from(metas).map(m => ({name: m.name, content: m.content}));

        // Check cookies
        result.cookies = document.cookie.split(';').map(c => c.trim().split('=')[0]).filter(n =>
            n.toLowerCase().includes('csrf') || n.toLowerCase().includes('xsrf') || n.toLowerCase().includes('token'));

        // Check for hidden inputs
        const hiddenInputs = document.querySelectorAll('input[type="hidden"]');
        result.hiddenInputs = Array.from(hiddenInputs).map(i => ({name: i.name, value: i.value?.substring(0, 50)}));

        // Check localStorage for tokens
        try {
            const keys = Object.keys(localStorage);
            result.localStorageKeys = keys;
            const tokenKeys = keys.filter(k =>
                k.toLowerCase().includes('token') || k.toLowerCase().includes('csrf') ||
                k.toLowerCase().includes('auth') || k.toLowerCase().includes('session'));
            result.tokenKeys = tokenKeys;
            result.tokenValues = {};
            for (const k of tokenKeys) {
                result.tokenValues[k] = localStorage.getItem(k)?.substring(0, 200);
            }
        } catch(e) {}

        return result;
    }""")
    print(f">>> CSRF/Token info: {json.dumps(csrf_info, indent=2, ensure_ascii=False)}")

    # ========================================
    # STEP 8: Examine the request headers of the successful personalization API call
    # ========================================
    print("\n\n>>> STEP 8: Examining how the site makes the personalizzazioni call...")

    # We need to intercept the actual XHR/Fetch calls the Angular app makes
    # Let's monkey-patch fetch to capture headers
    xhr_info = await page.evaluate("""async () => {
        // Intercept XMLHttpRequest
        const captured = [];
        const origOpen = XMLHttpRequest.prototype.open;
        const origSend = XMLHttpRequest.prototype.send;
        const origSetHeader = XMLHttpRequest.prototype.setRequestHeader;

        const headerStore = new Map();

        XMLHttpRequest.prototype.open = function(method, url, ...args) {
            this._capturedMethod = method;
            this._capturedUrl = url;
            this._capturedHeaders = {};
            return origOpen.call(this, method, url, ...args);
        };

        XMLHttpRequest.prototype.setRequestHeader = function(name, value) {
            if (this._capturedHeaders) {
                this._capturedHeaders[name] = value;
            }
            return origSetHeader.call(this, name, value);
        };

        XMLHttpRequest.prototype.send = function(body) {
            const self = this;
            const originalOnLoad = this.onload;
            this.addEventListener('load', function() {
                captured.push({
                    method: self._capturedMethod,
                    url: self._capturedUrl,
                    headers: self._capturedHeaders,
                    requestBody: body?.substring?.(0, 500) || String(body)?.substring(0, 500),
                    status: self.status,
                    responseLength: self.responseText?.length,
                });
            });
            return origSend.call(this, body);
        };

        // Wait a bit then trigger a navigation that should cause API calls
        // Navigate to home again
        window.location.hash = '';

        // Wait for any XHR calls
        await new Promise(resolve => setTimeout(resolve, 5000));

        return captured;
    }""")
    print(f">>> XHR intercepted: {json.dumps(xhr_info, indent=2, ensure_ascii=False)[:2000]}")

    # ========================================
    # STEP 9: Navigate around to trigger more API calls
    # ========================================
    print("\n\n>>> STEP 9: Navigating to trigger API calls with UI interaction...")

    # Try going to a specific store/category URL
    nav_urls = [
        "https://spesaonline.esselunga.it/commerce/nav/supermercato/store/category/id/600000001035269",
        "https://spesaonline.esselunga.it/commerce/nav/supermercato/store/search?query=latte",
        "https://spesaonline.esselunga.it/commerce/nav/supermercato/store/shelf",
    ]

    for nav_url in nav_urls:
        try:
            print(f"\n>>> Trying: {nav_url}")
            resp = await page.goto(nav_url, wait_until="domcontentloaded", timeout=15000)
            status = resp.status if resp else "?"
            print(f"    Status: {status}, Final URL: {page.url}")
            await page.wait_for_timeout(3000)
        except Exception as e:
            print(f"    Error: {str(e)[:100]}")

    # ========================================
    # STEP 10: Full analysis of leftMenuItemsHierarchy
    # ========================================
    print("\n\n>>> STEP 10: Full leftMenuItemsHierarchy tree...")

    full_tree = await page.evaluate("""async () => {
        try {
            const resp = await fetch("https://spesaonline.esselunga.it/commerce/resources/nav/supermercato", {
                headers: {'Accept': 'application/json'},
                credentials: 'include',
            });
            const data = await resp.json();

            // Build full tree from leftMenuItemsHierarchy
            function mapItem(item, depth) {
                const mapped = {
                    id: item.id,
                    label: item.label,
                    leaf: item.leaf,
                    showInMenu: item.showInMenu,
                    rootCategory: item.rootCategory,
                };
                if (item.menuItems && item.menuItems.length > 0 && depth < 3) {
                    mapped.children = item.menuItems.map(child => mapItem(child, depth + 1));
                } else if (item.menuItems) {
                    mapped.childCount = item.menuItems.length;
                }
                return mapped;
            }

            const tree = (data.leftMenuItemsHierarchy || []).map(item => mapItem(item, 0));

            // Also get leftMenuItems (flat list)
            const flatCount = data.leftMenuItems?.length || 0;
            const flatSample = data.leftMenuItems?.slice(0, 5).map(item => ({
                id: item.id,
                label: item.label,
                parentMenuItemId: item.parentMenuItemId,
                rootCategoryMenuItemId: item.rootCategoryMenuItemId,
                showInMenu: item.showInMenu,
                showInFilters: item.showInFilters,
                rootCategory: item.rootCategory,
                leaf: item.leaf,
                allKeys: Object.keys(item),
            }));

            return {
                treeCount: tree.length,
                tree: tree,
                flatCount: flatCount,
                flatSample: flatSample,
            };
        } catch (e) {
            return { error: e.message };
        }
    }""")
    print(f">>> Full tree: {json.dumps(full_tree, indent=2, ensure_ascii=False)}")

    # ========================================
    # STEP 11: Try POST with proper payloads for search
    # ========================================
    print("\n\n>>> STEP 11: Testing POST search with various payloads...")

    post_tests = [
        # Try different POST body formats
        {
            "desc": "POST search/supermercato with query in body",
            "url": "https://spesaonline.esselunga.it/commerce/resources/search/supermercato",
            "body": {"query": "latte"},
        },
        {
            "desc": "POST search with menuItemId",
            "url": "https://spesaonline.esselunga.it/commerce/resources/search/supermercato",
            "body": {"menuItemId": 600000001035269},
        },
        {
            "desc": "POST search/personalizzazioni with navigation",
            "url": "https://spesaonline.esselunga.it/commerce/resources/search/personalizzazioni",
            "body": {"navigation": "supermercato"},
        },
        {
            "desc": "POST nav/supermercato/search",
            "url": "https://spesaonline.esselunga.it/commerce/resources/nav/supermercato/search",
            "body": {"query": "latte"},
        },
        {
            "desc": "POST search/text/supermercato",
            "url": "https://spesaonline.esselunga.it/commerce/resources/search/text/supermercato",
            "body": {"query": "latte"},
        },
    ]

    for test in post_tests:
        body_json = json.dumps(test["body"])
        url = test["url"]
        result = await page.evaluate(f"""async () => {{
            try {{
                const resp = await fetch("{url}", {{
                    method: 'POST',
                    headers: {{
                        'Accept': 'application/json',
                        'Content-Type': 'application/json',
                    }},
                    credentials: 'include',
                    body: JSON.stringify({body_json}),
                }});
                const text = await resp.text();
                return {{
                    status: resp.status,
                    bodyLength: text.length,
                    body: text.substring(0, 2000),
                    headers: Object.fromEntries(resp.headers.entries()),
                }};
            }} catch (e) {{
                return {{ error: e.message }};
            }}
        }}""")
        print(f"\n  {test['desc']}")
        print(f"  -> {result.get('status', '?')} (size: {result.get('bodyLength', 0)})")
        if result.get('body'):
            print(f"  -> {result['body'][:400]}")

    # ========================================
    # STEP 12: Look at what the Angular app actually sends
    # ========================================
    print("\n\n>>> STEP 12: Intercepting actual XHR from Angular app navigation...")

    # Navigate fresh to the page and intercept all XHR
    intercept_result = await page.evaluate("""async () => {
        const captured = [];

        // Patch XMLHttpRequest
        const origOpen = XMLHttpRequest.prototype.open;
        const origSend = XMLHttpRequest.prototype.send;
        const origSetHeader = XMLHttpRequest.prototype.setRequestHeader;

        XMLHttpRequest.prototype.open = function(method, url, ...args) {
            this._xhrCapture = { method, url, headers: {} };
            return origOpen.call(this, method, url, ...args);
        };
        XMLHttpRequest.prototype.setRequestHeader = function(name, value) {
            if (this._xhrCapture) this._xhrCapture.headers[name] = value;
            return origSetHeader.call(this, name, value);
        };
        XMLHttpRequest.prototype.send = function(body) {
            if (this._xhrCapture) {
                this._xhrCapture.body = typeof body === 'string' ? body?.substring(0, 1000) : null;
                const self = this;
                this.addEventListener('loadend', function() {
                    self._xhrCapture.status = self.status;
                    self._xhrCapture.responseSize = self.responseText?.length || 0;
                    self._xhrCapture.responsePreview = self.responseText?.substring(0, 500) || '';
                    captured.push(self._xhrCapture);
                });
            }
            return origSend.call(this, body);
        };

        // Also patch fetch
        const origFetch = window.fetch;
        window.fetch = async function(input, init) {
            const url = typeof input === 'string' ? input : input.url;
            const method = init?.method || 'GET';
            const headers = init?.headers || {};
            const body = init?.body;

            const resp = await origFetch.call(this, input, init);
            const clone = resp.clone();
            const text = await clone.text().catch(() => '');

            captured.push({
                source: 'fetch',
                method,
                url,
                headers: typeof headers === 'object' ? headers : {},
                body: typeof body === 'string' ? body?.substring(0, 1000) : null,
                status: resp.status,
                responseSize: text.length,
                responsePreview: text.substring(0, 500),
            });

            return resp;
        };

        // Wait for any background calls
        await new Promise(resolve => setTimeout(resolve, 3000));

        return captured;
    }""")
    print(f">>> Intercepted calls after patching: {json.dumps(intercept_result, indent=2, ensure_ascii=False)[:3000]}")

    # Now navigate to trigger actual API calls
    print("\n>>> Navigating to trigger Angular routing...")

    # Try using Angular's router
    angular_nav = await page.evaluate("""async () => {
        const captured = [];

        // Check if there's an Angular scope with navigation methods
        if (window.angular) {
            const scope = window.angular.element(document.body).scope();
            if (scope) {
                return {
                    scopeKeys: Object.keys(scope).filter(k => !k.startsWith('$')).slice(0, 30),
                    hasCtrl: !!scope.pageCtrl || !!scope.ctrl,
                    pageCtrlKeys: scope.pageCtrl ? Object.keys(scope.pageCtrl).filter(k => typeof scope.pageCtrl[k] !== 'function').slice(0, 30) : null,
                };
            }
        }
        return { noAngular: true };
    }""")
    print(f">>> Angular scope: {json.dumps(angular_nav, indent=2, ensure_ascii=False)}")

    # ========================================
    # SUMMARY
    # ========================================
    print(f"\n\n{'='*80}")
    print(f"FINAL SUMMARY: {len(api_calls)} API calls captured")
    print(f"{'='*80}")

    for i, call in enumerate(api_calls):
        print(f"\n[{i+1}] [{call.get('method', '?')}] {call['status']} {call['url']}")
        print(f"    Size: {call['body_length']} | Type: {call['content_type']}")
        if call.get('request_body'):
            print(f"    Req: {call['request_body'][:200]}")

    all_data = {
        "api_calls": api_calls,
        "full_tree": full_tree if isinstance(full_tree, dict) else None,
    }
    with open("/tmp/esselunga_api_calls.json", "w") as f:
        json.dump(all_data, f, indent=2, default=str, ensure_ascii=False)
    print("\n>>> Data saved to /tmp/esselunga_api_calls.json")

    await browser.close()
    await pw.stop()
    print("\n>>> Done!")


if __name__ == "__main__":
    asyncio.run(main())
