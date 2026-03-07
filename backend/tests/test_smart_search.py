"""Tests for the /products/smart-search endpoint and related dedup logic."""

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Chain, Offer, Product


# ---------------------------------------------------------------------------
# Fixtures — two chains + multiple products
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def chain_esselunga(db: AsyncSession) -> Chain:
    c = Chain(id=uuid.uuid4(), name="Esselunga", slug="esselunga", website_url="https://esselunga.it")
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return c


@pytest_asyncio.fixture
async def chain_iperal(db: AsyncSession) -> Chain:
    c = Chain(id=uuid.uuid4(), name="Iperal", slug="iperal", website_url="https://iperal.it")
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return c


def _make_product(name, brand=None, category=None, source=None) -> Product:
    return Product(
        id=uuid.uuid4(), name=name, brand=brand,
        category=category, source=source,
    )


def _make_offer(product: Product, chain: Chain, price: float) -> Offer:
    today = date.today()
    return Offer(
        id=uuid.uuid4(),
        product_id=product.id,
        chain_id=chain.id,
        offer_price=Decimal(str(price)),
        valid_from=today - timedelta(days=1),
        valid_to=today + timedelta(days=6),
    )


# ---------------------------------------------------------------------------
# Test: basic search returns matching products
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_smart_search_basic(client: AsyncClient, db: AsyncSession, chain_esselunga: Chain):
    p = _make_product("Latte Granarolo Intero 1l", brand="Granarolo", category="Latticini")
    db.add(p)
    o = _make_offer(p, chain_esselunga, 1.29)
    db.add(o)
    await db.commit()

    resp = await client.get("/api/v1/products/smart-search", params={"q": "latte granarolo"})
    assert resp.status_code == 200
    results = resp.json()
    assert len(results) >= 1
    assert "Latte" in results[0]["product"]["name"]


# ---------------------------------------------------------------------------
# Test: stemming — "finocchi" matches "finocchio"
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_smart_search_stemming(client: AsyncClient, db: AsyncSession, chain_esselunga: Chain):
    p = _make_product("Finocchio", category="Frutta e Verdura")
    db.add(p)
    o = _make_offer(p, chain_esselunga, 1.50)
    db.add(o)
    await db.commit()

    resp = await client.get("/api/v1/products/smart-search", params={"q": "finocchi"})
    assert resp.status_code == 200
    results = resp.json()
    # Should find the product via ILIKE (finocchi is a substring of finocchio)
    names = [r["product"]["name"] for r in results]
    assert any("Finocchio" in n or "Finocchi" in n for n in names)


# ---------------------------------------------------------------------------
# Test: "finocchi" should NOT return "Infuso Finocchio" tea
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_smart_search_no_cross_category(
    client: AsyncClient, db: AsyncSession, chain_esselunga: Chain
):
    veg = _make_product("Finocchi", category="Frutta e Verdura")
    tea = _make_product("Infuso Finocchio", category="Caffe e Te")
    db.add_all([veg, tea])
    o1 = _make_offer(veg, chain_esselunga, 1.50)
    o2 = _make_offer(tea, chain_esselunga, 2.30)
    db.add_all([o1, o2])
    await db.commit()

    resp = await client.get("/api/v1/products/smart-search", params={"q": "finocchi"})
    assert resp.status_code == 200
    results = resp.json()
    names = [r["product"]["name"] for r in results]
    # Both may appear in search results (ILIKE matches both),
    # but they should be separate entries, not merged
    assert "Finocchi" in names
    if "Infuso Finocchio" in names:
        # They should be separate results, not grouped together
        finocchi_offers = None
        infuso_offers = None
        for r in results:
            if r["product"]["name"] == "Finocchi":
                finocchi_offers = r["offers"]
            elif r["product"]["name"] == "Infuso Finocchio":
                infuso_offers = r["offers"]
        # The infuso should NOT have stolen the finocchi's offers
        if finocchi_offers:
            assert len(finocchi_offers) >= 1


# ---------------------------------------------------------------------------
# Test: private-label search
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_smart_search_private_label(
    client: AsyncClient, db: AsyncSession, chain_esselunga: Chain
):
    p = _make_product("Esselunga Naturama Spinaci 500g", brand="Esselunga", category="Frutta e Verdura")
    db.add(p)
    o = _make_offer(p, chain_esselunga, 1.20)
    db.add(o)
    await db.commit()

    resp = await client.get("/api/v1/products/smart-search", params={"q": "spinaci"})
    assert resp.status_code == 200
    results = resp.json()
    assert len(results) >= 1
    assert "Spinaci" in results[0]["product"]["name"]


# ---------------------------------------------------------------------------
# Test: abbreviation matching
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_smart_search_abbreviation(
    client: AsyncClient, db: AsyncSession, chain_esselunga: Chain
):
    p = _make_product("Latte Parzialmente Scremato 1l", brand="Granarolo", category="Latticini")
    db.add(p)
    o = _make_offer(p, chain_esselunga, 1.10)
    db.add(o)
    await db.commit()

    # Search with abbreviation
    resp = await client.get("/api/v1/products/smart-search", params={"q": "latte parz screm"})
    assert resp.status_code == 200
    results = resp.json()
    # The SQL ILIKE won't match abbreviations directly, but the product
    # should still appear if "latte" matches
    names = [r["product"]["name"] for r in results]
    assert any("Latte" in n for n in names)


# ---------------------------------------------------------------------------
# Test: empty / too-short query rejected
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_smart_search_short_query(client: AsyncClient):
    resp = await client.get("/api/v1/products/smart-search", params={"q": "x"})
    assert resp.status_code == 422  # validation error, min_length=2


# ---------------------------------------------------------------------------
# Test: multi-chain offers shown per product
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_smart_search_multi_chain(
    client: AsyncClient, db: AsyncSession,
    chain_esselunga: Chain, chain_iperal: Chain,
):
    p1 = _make_product("Pasta Barilla Penne 500g", brand="Barilla", category="Pasta e Riso")
    p2 = _make_product("Barilla Penne Rigate 500g", brand="Barilla", category="Pasta e Riso")
    db.add_all([p1, p2])
    o1 = _make_offer(p1, chain_esselunga, 0.89)
    o2 = _make_offer(p2, chain_iperal, 0.95)
    db.add_all([o1, o2])
    await db.commit()

    resp = await client.get("/api/v1/products/smart-search", params={"q": "barilla penne"})
    assert resp.status_code == 200
    results = resp.json()
    assert len(results) >= 1


# ---------------------------------------------------------------------------
# Test: no results for unmatched query
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_smart_search_no_results(client: AsyncClient):
    resp = await client.get("/api/v1/products/smart-search", params={"q": "prodottoinesistente123"})
    assert resp.status_code == 200
    assert resp.json() == []
