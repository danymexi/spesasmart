"""SpesaSmart API - Main FastAPI application."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.api import auth, chains, flyers, offers, products, scraping, stores, users
from app.api import web_push
from app.config import get_settings

# Path to Expo web build output (copied into Docker image)
DIST_DIR = Path(__file__).resolve().parent.parent / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    if settings.scheduler_enabled:
        from app.jobs.scheduler import start_scheduler

        scheduler = start_scheduler()
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
app.include_router(web_push.router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok"}


# ── Static files + SPA fallback ──────────────────────────────────────────────

if DIST_DIR.is_dir():
    # Serve static assets (JS bundles, images, etc.)
    app.mount("/_expo", StaticFiles(directory=DIST_DIR / "_expo"), name="expo-assets")

    # Serve files in the root of dist (manifest.json, sw.js, pwa-icons, etc.)
    @app.get("/manifest.json")
    async def manifest():
        return FileResponse(DIST_DIR / "manifest.json")

    @app.get("/sw.js")
    async def service_worker():
        return FileResponse(
            DIST_DIR / "sw.js",
            media_type="application/javascript",
            headers={"Service-Worker-Allowed": "/"},
        )

    # Serve PWA icons
    if (DIST_DIR / "pwa-icons").is_dir():
        app.mount("/pwa-icons", StaticFiles(directory=DIST_DIR / "pwa-icons"), name="pwa-icons")

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

        # Otherwise serve index.html (SPA routing)
        index = DIST_DIR / "index.html"
        if index.is_file():
            return FileResponse(index)

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
