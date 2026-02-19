"""Pytest fixtures for SpesaSmart backend tests."""

import asyncio
import uuid
from datetime import date, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base, get_db
from app.main import app
from app.models import Chain, Flyer, Offer, Product, Store, UserProfile


# Use SQLite for tests (in-memory)
TEST_DATABASE_URL = "sqlite+aiosqlite:///./test.db"

engine = create_async_engine(TEST_DATABASE_URL, echo=False)
test_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def override_get_db():
    async with test_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


app.dependency_overrides[get_db] = override_get_db


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def db():
    async with test_session() as session:
        yield session


@pytest_asyncio.fixture
async def sample_chain(db: AsyncSession) -> Chain:
    chain = Chain(
        id=uuid.uuid4(),
        name="Esselunga",
        slug="esselunga",
        website_url="https://esselunga.it",
    )
    db.add(chain)
    await db.commit()
    await db.refresh(chain)
    return chain


@pytest_asyncio.fixture
async def sample_store(db: AsyncSession, sample_chain: Chain) -> Store:
    store = Store(
        id=uuid.uuid4(),
        chain_id=sample_chain.id,
        name="Esselunga Monza",
        address="Via Test 1",
        city="Monza",
        province="MB",
        zip_code="20900",
    )
    db.add(store)
    await db.commit()
    await db.refresh(store)
    return store


@pytest_asyncio.fixture
async def sample_product(db: AsyncSession) -> Product:
    product = Product(
        id=uuid.uuid4(),
        name="Latte Granarolo PS 1L",
        brand="Granarolo",
        category="Latticini",
        unit="l",
    )
    db.add(product)
    await db.commit()
    await db.refresh(product)
    return product


@pytest_asyncio.fixture
async def sample_flyer(db: AsyncSession, sample_chain: Chain) -> Flyer:
    today = date.today()
    flyer = Flyer(
        id=uuid.uuid4(),
        chain_id=sample_chain.id,
        title="Offerte della settimana",
        valid_from=today - timedelta(days=1),
        valid_to=today + timedelta(days=6),
        status="completed",
    )
    db.add(flyer)
    await db.commit()
    await db.refresh(flyer)
    return flyer


@pytest_asyncio.fixture
async def sample_offer(
    db: AsyncSession,
    sample_product: Product,
    sample_flyer: Flyer,
    sample_chain: Chain,
) -> Offer:
    today = date.today()
    offer = Offer(
        id=uuid.uuid4(),
        product_id=sample_product.id,
        flyer_id=sample_flyer.id,
        chain_id=sample_chain.id,
        original_price=1.89,
        offer_price=1.29,
        discount_pct=31.75,
        discount_type="percentage",
        valid_from=today - timedelta(days=1),
        valid_to=today + timedelta(days=6),
    )
    db.add(offer)
    await db.commit()
    await db.refresh(offer)
    return offer


@pytest_asyncio.fixture
async def sample_user(db: AsyncSession) -> UserProfile:
    user = UserProfile(
        id=uuid.uuid4(),
        telegram_chat_id=123456789,
        preferred_zone="Monza e Brianza",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user
