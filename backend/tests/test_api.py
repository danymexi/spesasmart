"""Tests for API endpoints."""

import pytest
from httpx import AsyncClient

from app.models import Chain, Flyer, Offer, Product, Store, UserProfile


@pytest.mark.asyncio
async def test_root(client: AsyncClient):
    resp = await client.get("/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["app"] == "SpesaSmart"


@pytest.mark.asyncio
async def test_health(client: AsyncClient):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


# --- Chains ---

@pytest.mark.asyncio
async def test_list_chains(client: AsyncClient, sample_chain: Chain):
    resp = await client.get("/api/v1/chains")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert data[0]["name"] == "Esselunga"


@pytest.mark.asyncio
async def test_get_chain(client: AsyncClient, sample_chain: Chain):
    resp = await client.get(f"/api/v1/chains/{sample_chain.id}")
    assert resp.status_code == 200
    assert resp.json()["slug"] == "esselunga"


@pytest.mark.asyncio
async def test_get_chain_not_found(client: AsyncClient):
    resp = await client.get("/api/v1/chains/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


# --- Stores ---

@pytest.mark.asyncio
async def test_list_stores(client: AsyncClient, sample_store: Store):
    resp = await client.get("/api/v1/stores")
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


@pytest.mark.asyncio
async def test_list_stores_filter_city(client: AsyncClient, sample_store: Store):
    resp = await client.get("/api/v1/stores", params={"city": "Monza"})
    assert resp.status_code == 200
    stores = resp.json()
    assert all("Monza" in s["city"] for s in stores)


# --- Flyers ---

@pytest.mark.asyncio
async def test_list_active_flyers(client: AsyncClient, sample_flyer: Flyer):
    resp = await client.get("/api/v1/flyers")
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


@pytest.mark.asyncio
async def test_get_flyer(client: AsyncClient, sample_flyer: Flyer):
    resp = await client.get(f"/api/v1/flyers/{sample_flyer.id}")
    assert resp.status_code == 200
    assert resp.json()["title"] == "Offerte della settimana"


# --- Products ---

@pytest.mark.asyncio
async def test_search_products(client: AsyncClient, sample_product: Product):
    resp = await client.get("/api/v1/products/search", params={"q": "latte"})
    assert resp.status_code == 200
    results = resp.json()
    assert len(results) >= 1
    assert "Latte" in results[0]["product"]["name"]


@pytest.mark.asyncio
async def test_get_product(client: AsyncClient, sample_product: Product):
    resp = await client.get(f"/api/v1/products/{sample_product.id}")
    assert resp.status_code == 200
    assert resp.json()["brand"] == "Granarolo"


@pytest.mark.asyncio
async def test_product_best_price(
    client: AsyncClient, sample_product: Product, sample_offer: Offer
):
    resp = await client.get(f"/api/v1/products/{sample_product.id}/best-price")
    assert resp.status_code == 200
    data = resp.json()
    assert float(data["best_price"]) == 1.29


@pytest.mark.asyncio
async def test_product_price_history(
    client: AsyncClient, sample_product: Product, sample_offer: Offer
):
    resp = await client.get(f"/api/v1/products/{sample_product.id}/history")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["history"]) >= 1


# --- Offers ---

@pytest.mark.asyncio
async def test_active_offers(client: AsyncClient, sample_offer: Offer):
    resp = await client.get("/api/v1/offers/active")
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


@pytest.mark.asyncio
async def test_best_offers(client: AsyncClient, sample_offer: Offer):
    resp = await client.get("/api/v1/offers/best")
    assert resp.status_code == 200


# --- Users ---

@pytest.mark.asyncio
async def test_create_user(client: AsyncClient):
    resp = await client.post(
        "/api/v1/users",
        json={"telegram_chat_id": 999999, "preferred_zone": "Monza"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["telegram_chat_id"] == 999999


@pytest.mark.asyncio
async def test_get_user(client: AsyncClient, sample_user: UserProfile):
    resp = await client.get(f"/api/v1/users/{sample_user.id}")
    assert resp.status_code == 200
    assert resp.json()["preferred_zone"] == "Monza e Brianza"


@pytest.mark.asyncio
async def test_watchlist_flow(
    client: AsyncClient,
    sample_user: UserProfile,
    sample_product: Product,
):
    # Add to watchlist
    resp = await client.post(
        f"/api/v1/users/{sample_user.id}/watchlist",
        json={"product_id": str(sample_product.id), "target_price": 1.50},
    )
    assert resp.status_code == 201
    assert resp.json()["product_name"] == sample_product.name

    # Get watchlist
    resp = await client.get(f"/api/v1/users/{sample_user.id}/watchlist")
    assert resp.status_code == 200
    assert len(resp.json()) == 1

    # Remove from watchlist
    resp = await client.delete(
        f"/api/v1/users/{sample_user.id}/watchlist/{sample_product.id}"
    )
    assert resp.status_code == 204

    # Verify removed
    resp = await client.get(f"/api/v1/users/{sample_user.id}/watchlist")
    assert resp.status_code == 200
    assert len(resp.json()) == 0


@pytest.mark.asyncio
async def test_user_deals(
    client: AsyncClient,
    sample_user: UserProfile,
    sample_product: Product,
    sample_offer: Offer,
):
    # Add product to watchlist first
    await client.post(
        f"/api/v1/users/{sample_user.id}/watchlist",
        json={"product_id": str(sample_product.id)},
    )

    # Get deals
    resp = await client.get(f"/api/v1/users/{sample_user.id}/deals")
    assert resp.status_code == 200
    deals = resp.json()
    assert len(deals) >= 1
    assert float(deals[0]["offer_price"]) == 1.29
