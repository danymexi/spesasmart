from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from routers import products, stores, lists, compare, auth


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    yield
    # Shutdown


app = FastAPI(
    title="GroceryCompass API",
    description="API per il confronto prezzi dei supermercati italiani",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/v1/auth", tags=["auth"])
app.include_router(products.router, prefix="/v1/products", tags=["products"])
app.include_router(stores.router, prefix="/v1/stores", tags=["stores"])
app.include_router(lists.router, prefix="/v1/lists", tags=["lists"])
app.include_router(compare.router, prefix="/v1/lists", tags=["compare"])


@app.get("/health")
async def health_check():
    return {"status": "ok"}
