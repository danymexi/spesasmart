"""Base scraper class for supermarket product scraping."""

import asyncio
import hashlib
import logging
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import AsyncIterator

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
]


@dataclass
class RawProduct:
    external_id: str
    name: str
    brand: str | None = None
    price: float = 0.0
    price_discounted: float | None = None
    discount_label: str | None = None
    discount_ends: str | None = None
    quantity_raw: str = ""
    barcode_ean: str | None = None
    image_url: str | None = None
    product_url: str = ""
    category_raw: str | None = None
    scraped_at: datetime = field(default_factory=datetime.utcnow)

    def compute_hash(self) -> str:
        """Hash the key fields to detect price changes."""
        data = f"{self.external_id}|{self.price}|{self.price_discounted}|{self.discount_label}|{self.name}"
        return hashlib.sha256(data.encode()).hexdigest()


class BaseSupermarketScraper(ABC):
    CHAIN_SLUG: str = ""
    RATE_LIMIT_DELAY: float = 2.0
    MAX_RETRIES: int = 3

    def __init__(self):
        self.logger = logging.getLogger(f"scraper.{self.CHAIN_SLUG}")
        self.products_scraped = 0
        self.errors = []

    @abstractmethod
    async def scrape_all_products(self) -> AsyncIterator[RawProduct]:
        """Scrape all products from the supermarket."""
        yield  # type: ignore

    @abstractmethod
    async def scrape_category(self, category_url: str) -> list[RawProduct]:
        """Scrape products from a specific category page."""
        pass

    async def rate_limit(self):
        """Wait between requests to avoid overwhelming the server."""
        delay = self.RATE_LIMIT_DELAY + random.uniform(0, 1)
        await asyncio.sleep(delay)

    async def retry_with_backoff(self, coro, *args, **kwargs):
        """Retry a coroutine with exponential backoff."""
        for attempt in range(self.MAX_RETRIES):
            try:
                return await coro(*args, **kwargs)
            except Exception as e:
                if attempt == self.MAX_RETRIES - 1:
                    raise
                wait = (2 ** attempt) + random.uniform(0, 1)
                self.logger.warning(
                    f"Attempt {attempt + 1} failed: {e}. Retrying in {wait:.1f}s"
                )
                await asyncio.sleep(wait)
