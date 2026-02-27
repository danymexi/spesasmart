"""Database connection and session management."""

import re
import socket

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

settings = get_settings()


def _resolve_database_url(url: str) -> str:
    """Resolve DB hostname to IPv6 if standard DNS resolution fails.

    Supabase free-tier projects may only have AAAA (IPv6) DNS records.
    Python's ``socket.getaddrinfo`` sometimes fails to resolve these on
    macOS, so we fall back to ``dig`` to obtain the IPv6 address and
    embed it directly in the connection URL.
    """
    match = re.search(r"@([^/:]+)", url)
    if not match:
        return url
    host = match.group(1)

    # Check if Python can resolve the host normally.
    try:
        socket.getaddrinfo(host, 5432, socket.AF_UNSPEC, socket.SOCK_STREAM)
        return url
    except socket.gaierror:
        pass

    # Fallback: use ``dig`` for IPv6 resolution.
    import logging
    import subprocess

    logger = logging.getLogger(__name__)

    try:
        result = subprocess.run(
            ["dig", "+short", "AAAA", host],
            capture_output=True, text=True, timeout=5,
        )
        ipv6_addr = result.stdout.strip().split("\n")[0].strip()
        if ipv6_addr and ":" in ipv6_addr:
            new_url = url.replace(f"@{host}", f"@[{ipv6_addr}]")
            logger.info("Resolved DB host %s -> IPv6 %s", host, ipv6_addr)
            return new_url
    except Exception:
        pass

    logger.warning("Could not resolve DB host: %s", host)
    return url


_db_url = _resolve_database_url(settings.database_url)

engine = create_async_engine(
    _db_url,
    echo=settings.debug,
    pool_size=5,
    max_overflow=10,
)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
