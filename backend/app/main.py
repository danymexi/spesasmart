"""SpesaSmart API - Main FastAPI application."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

# Configure root logger so application logs (scrapers, services, etc.)
# are visible alongside uvicorn's access logs.
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s:%(name)s: %(message)s",
)

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from app.api import auth, chains, flyers, offers, products, purchases, scraping, stores, users
from app.api import web_push
from app.config import get_settings
from app.database import async_session

# Path to Expo web build output (copied into Docker image)
DIST_DIR = Path(__file__).resolve().parent.parent / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    if settings.scheduler_enabled:
        import asyncio
        from app.jobs.scheduler import check_freshness_and_scrape, start_scheduler

        scheduler = start_scheduler()
        asyncio.create_task(check_freshness_and_scrape())
        yield
        scheduler.shutdown()
    else:
        yield


settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    description="API per il confronto prezzi dei supermercati in Monza e Brianza",
    version="1.0.0",
    lifespan=lifespan,
)

class NoCdnCacheMiddleware(BaseHTTPMiddleware):
    """Tell Cloudflare CDN to never cache HTML pages and service worker."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        path = request.url.path
        ct = response.headers.get("content-type", "")
        # Never let CDN cache HTML, service worker, or manifest
        if (
            "text/html" in ct
            or path in ("/sw.js", "/manifest.json")
            or path == "/"
        ):
            response.headers["CDN-Cache-Control"] = "no-store"
            response.headers["Cloudflare-CDN-Cache-Control"] = "no-store"
        return response


app.add_middleware(NoCdnCacheMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routers
app.include_router(auth.router, prefix="/api/v1")
app.include_router(chains.router, prefix="/api/v1")
app.include_router(stores.router, prefix="/api/v1")
app.include_router(flyers.router, prefix="/api/v1")
app.include_router(products.router, prefix="/api/v1")
app.include_router(offers.router, prefix="/api/v1")
app.include_router(users.router, prefix="/api/v1")
app.include_router(scraping.router, prefix="/api/v1")
app.include_router(purchases.router, prefix="/api/v1")
app.include_router(web_push.router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok"}


# ── Static files + SPA fallback ──────────────────────────────────────────────

if DIST_DIR.is_dir():
    # Serve static assets (JS bundles, images, fonts, etc.)
    app.mount("/_expo", StaticFiles(directory=DIST_DIR / "_expo"), name="expo-assets")

    # Serve fonts from a flat directory (Cloudflare rejects @ in URLs, so
    # the deep node_modules path doesn't work through the tunnel)
    if (DIST_DIR / "fonts").is_dir():
        app.mount("/fonts", StaticFiles(directory=DIST_DIR / "fonts"), name="web-fonts")

    # Rewrite deep asset paths containing @ to the flat /fonts/ directory
    @app.get("/assets/{rest:path}")
    async def assets_rewrite(rest: str):
        """Serve assets; for font files, redirect to /fonts/ to avoid @ in URL."""
        # Check if it's a font file request
        if rest.endswith(".ttf"):
            import os
            font_name = os.path.basename(rest)
            font_path = DIST_DIR / "fonts" / font_name
            if font_path.is_file():
                return FileResponse(font_path, media_type="font/ttf")

        # Otherwise try serving from the full assets tree
        asset_path = DIST_DIR / "assets" / rest
        if asset_path.is_file():
            return FileResponse(asset_path)

        return HTMLResponse(status_code=404, content="Not Found")

    # Serve files in the root of dist (manifest.json, sw.js, pwa-icons, etc.)
    @app.get("/manifest.json")
    async def manifest():
        return FileResponse(DIST_DIR / "manifest.json")

    @app.get("/sw.js")
    async def service_worker():
        return FileResponse(
            DIST_DIR / "sw.js",
            media_type="application/javascript",
            headers={
                "Service-Worker-Allowed": "/",
                "Cache-Control": "no-cache, no-store, must-revalidate",
            },
        )

    # Serve PWA icons
    if (DIST_DIR / "pwa-icons").is_dir():
        app.mount("/pwa-icons", StaticFiles(directory=DIST_DIR / "pwa-icons"), name="pwa-icons")

    async def _get_product_og_html(product_id: str) -> str | None:
        """Generate HTML with OG meta tags for a product page (for social previews)."""
        import re
        import uuid as uuid_mod
        from datetime import date

        from sqlalchemy import select
        from sqlalchemy.orm import joinedload
        from app.models import Chain, Offer, Product

        try:
            pid = uuid_mod.UUID(product_id)
        except ValueError:
            return None

        async with async_session() as session:
            result = await session.execute(
                select(Product).where(Product.id == pid)
            )
            product = result.scalar_one_or_none()
            if not product:
                return None

            # Find best active offer
            today = date.today()
            offer_result = await session.execute(
                select(Offer)
                .options(joinedload(Offer.chain))
                .where(
                    Offer.product_id == pid,
                    Offer.valid_from <= today,
                    Offer.valid_to >= today,
                )
                .order_by(Offer.offer_price)
                .limit(1)
            )
            best = offer_result.unique().scalar_one_or_none()

            title = f"{product.name} - SpesaSmart"
            description = product.brand or ""
            if best:
                discount = f" (-{best.discount_pct:.0f}%)" if best.discount_pct else ""
                description = f"{best.offer_price:.2f}\u20ac{discount} da {best.chain.name if best.chain else ''}"
                if product.brand:
                    description = f"{product.brand} - {description}"

            image = product.image_url or ""
            url = f"https://spesasmart.spazioitech.it/product/{product_id}"

            # Read the original index.html and inject OG tags
            index = DIST_DIR / "index.html"
            if not index.is_file():
                return None

            html = index.read_text()

            # Escape for HTML attributes
            def esc(s: str) -> str:
                return s.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;")

            og_tags = (
                f'<meta property="og:title" content="{esc(title)}" />\n'
                f'<meta property="og:description" content="{esc(description)}" />\n'
                f'<meta property="og:url" content="{esc(url)}" />\n'
                f'<meta property="og:type" content="product" />\n'
                f'<meta property="og:site_name" content="SpesaSmart" />\n'
            )
            if image:
                og_tags += f'<meta property="og:image" content="{esc(image)}" />\n'

            # Insert before </head>
            html = html.replace("</head>", og_tags + "</head>", 1)
            return html

    # SPA fallback: any non-API, non-docs route serves index.html
    @app.get("/{full_path:path}")
    async def spa_fallback(request: Request, full_path: str):
        # Don't intercept API, docs, health, or openapi routes
        if full_path.startswith(("api/", "docs", "redoc", "openapi.json", "health")):
            return HTMLResponse(status_code=404, content="Not Found")

        # Try to serve a static file first
        static_file = DIST_DIR / full_path
        if static_file.is_file():
            return FileResponse(static_file)

        # Product pages: inject OG meta tags for social preview
        import re
        product_match = re.match(r"^product/([0-9a-f\-]{36})(?:/.*)?$", full_path)
        if product_match:
            og_html = await _get_product_og_html(product_match.group(1))
            if og_html:
                return HTMLResponse(
                    content=og_html,
                    headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
                )

        # Otherwise serve index.html (SPA routing)
        index = DIST_DIR / "index.html"
        if index.is_file():
            return FileResponse(
                index,
                headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
            )

        return HTMLResponse(status_code=404, content="Not Found")
else:
    @app.get("/")
    async def root():
        return {
            "app": "SpesaSmart",
            "version": "1.0.0",
            "docs": "/docs",
            "note": "Web app not built — serve API only",
        }
