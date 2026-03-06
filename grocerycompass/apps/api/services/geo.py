"""Geolocation services."""

import httpx


async def ip_geolocation(ip: str | None = None) -> dict | None:
    """Fallback geolocation using IP address."""
    try:
        url = f"https://ipapi.co/{ip}/json/" if ip else "https://ipapi.co/json/"
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(url)
            if response.status_code == 200:
                data = response.json()
                return {
                    "lat": data.get("latitude"),
                    "lng": data.get("longitude"),
                    "city": data.get("city"),
                    "region": data.get("region"),
                    "country": data.get("country_code"),
                }
    except Exception:
        pass
    return None


def haversine_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Calculate distance between two points in km using Haversine formula."""
    import math

    R = 6371  # Earth radius in km

    d_lat = math.radians(lat2 - lat1)
    d_lng = math.radians(lng2 - lng1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(d_lng / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c
