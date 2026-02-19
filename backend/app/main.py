"""SpesaSmart API - Main FastAPI application."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import chains, flyers, offers, products, scraping, stores, users
from app.config import get_settings


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
app.include_router(chains.router, prefix="/api/v1")
app.include_router(stores.router, prefix="/api/v1")
app.include_router(flyers.router, prefix="/api/v1")
app.include_router(products.router, prefix="/api/v1")
app.include_router(offers.router, prefix="/api/v1")
app.include_router(users.router, prefix="/api/v1")
app.include_router(scraping.router, prefix="/api/v1")


@app.get("/")
async def root():
    return {
        "app": "SpesaSmart",
        "version": "1.0.0",
        "docs": "/docs",
    }


@app.get("/health")
async def health():
    return {"status": "ok"}
