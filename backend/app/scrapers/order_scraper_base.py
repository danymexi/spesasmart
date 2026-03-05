"""Base class for supermarket order history scrapers."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class OrderItem:
    """A single product line in an order."""
    external_name: str
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    total_price: Decimal | None = None
    external_code: str | None = None
    brand: str | None = None
    category: str | None = None


@dataclass
class Order:
    """A single order from a supermarket."""
    external_order_id: str
    order_date: datetime
    total_amount: Decimal | None = None
    store_name: str | None = None
    status: str | None = None
    items: list[OrderItem] = field(default_factory=list)
    raw_data: dict[str, Any] | None = None


class OrderScraperBase(ABC):
    """Abstract base for order history scrapers.

    Subclasses must implement login() and fetch_orders().
    """

    chain_slug: str = ""

    @abstractmethod
    async def login(self, email: str, password: str) -> bool:
        """Authenticate with the supermarket.

        Returns True on success, False on failure.
        Raises on unexpected errors.
        """

    @abstractmethod
    async def fetch_orders(self, since: datetime | None = None) -> list[Order]:
        """Fetch orders, optionally filtering to those after `since`.

        Must be called after a successful login().
        """

    async def close(self) -> None:
        """Clean up resources (browser, HTTP client, etc.)."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()
