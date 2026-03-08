"""Import supermarket store locations from OpenStreetMap (Overpass API).

Fetches all store locations for the 11 SpesaSmart chains across Italy
using the free Overpass API. No API key required.

Handles:
- Nodes (direct lat/lon) and ways/relations (center lat/lon via `out center`)
- Brand tag variants (e.g. "Carrefour Express" → carrefour, "MD" → md-discount)
- Address extraction from OSM addr:* tags
- Upsert via INSERT ... ON CONFLICT (osm_id) DO UPDATE in batches
- Idempotent — safe to re-run monthly for updates

Run from the backend directory:
    docker compose exec backend python -m app.scripts.import_osm_stores
    docker compose exec backend python -m app.scripts.import_osm_stores --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from collections import Counter
from dataclasses import dataclass

import httpx
from sqlalchemy import select, text

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
BATCH_SIZE = 200

# Each chain gets its own Overpass query to avoid timeouts.
# Format: (chain_slug, overpass_filter_lines)
# Using exact brand= where possible, regex only for variants.
CHAIN_QUERIES: list[tuple[str, str]] = [
    ("esselunga", """
  nwr["brand"="Esselunga"]["shop"="supermarket"](area.italy);
  nwr["brand"="laEsse"]["shop"](area.italy);
  nwr["brand"="La Esse"]["shop"](area.italy);
"""),
    ("lidl", """
  nwr["brand"="Lidl"]["shop"="supermarket"](area.italy);
"""),
    ("coop", """
  nwr["brand"~"^Coop$"]["shop"="supermarket"](area.italy);
  nwr["brand"~"^Coop "]["shop"="supermarket"](area.italy);
  nwr["brand"="InCoop"]["shop"="supermarket"](area.italy);
"""),
    ("iperal", """
  nwr["brand"="Iperal"]["shop"="supermarket"](area.italy);
"""),
    ("carrefour", """
  nwr["brand"~"^Carrefour"]["shop"="supermarket"](area.italy);
"""),
    ("conad", """
  nwr["brand"~"^Conad"]["shop"="supermarket"](area.italy);
"""),
    ("eurospin", """
  nwr["brand"="Eurospin"]["shop"="supermarket"](area.italy);
"""),
    ("aldi", """
  nwr["brand"~"^Aldi"]["shop"="supermarket"](area.italy);
"""),
    ("md-discount", """
  nwr["brand"~"^MD"]["shop"="supermarket"](area.italy);
  nwr["name"="MD"]["shop"="supermarket"](area.italy);
"""),
    ("penny", """
  nwr["brand"~"^Penny"]["shop"="supermarket"](area.italy);
"""),
    ("pam", """
  nwr["brand"~"^PAM"]["shop"="supermarket"](area.italy);
  nwr["brand"="Panorama"]["shop"="supermarket"](area.italy);
  nwr["brand"~"^Pam"]["shop"="supermarket"](area.italy);
"""),
]


@dataclass
class OsmStore:
    """Parsed store data from an OSM element."""
    osm_id: int
    chain_slug: str
    name: str | None
    address: str | None
    city: str | None
    province: str | None
    zip_code: str | None
    lat: float
    lon: float
    phone: str | None
    opening_hours: str | None


def _parse_elements(elements: list[dict], chain_slug: str) -> list[OsmStore]:
    """Parse Overpass JSON elements into OsmStore objects."""
    stores: list[OsmStore] = []
    seen_ids: set[int] = set()

    for el in elements:
        osm_id = el.get("id")
        if not osm_id or osm_id in seen_ids:
            continue

        tags = el.get("tags", {})

        # Determine lat/lon: nodes have direct coords, ways/relations use center
        if el["type"] == "node":
            lat = el.get("lat")
            lon = el.get("lon")
        else:
            center = el.get("center", {})
            lat = center.get("lat")
            lon = center.get("lon")

        if lat is None or lon is None:
            continue

        # Build address from addr:* tags
        street = tags.get("addr:street", "")
        housenumber = tags.get("addr:housenumber", "")
        address = f"{street} {housenumber}".strip() or None

        name = (tags.get("name") or tags.get("brand") or "")[:200] or None
        city = (tags.get("addr:city") or tags.get("addr:hamlet") or "")[:100] or None

        # Province: OSM may have full name ("Barletta-Andria-Trani"),
        # but our column is VARCHAR(10). Truncate to fit.
        province_raw = tags.get("addr:province") or ""
        province = province_raw[:10] if province_raw else None

        stores.append(OsmStore(
            osm_id=osm_id,
            chain_slug=chain_slug,
            name=name,
            address=address,
            city=city,
            province=province,
            zip_code=(tags.get("addr:postcode") or "")[:10] or None,
            lat=round(lat, 7),
            lon=round(lon, 7),
            phone=(tags.get("phone") or tags.get("contact:phone") or "")[:30] or None,
            opening_hours=tags.get("opening_hours"),
        ))
        seen_ids.add(osm_id)

    return stores


async def fetch_chain_stores(
    client: httpx.AsyncClient, chain_slug: str, filter_lines: str
) -> list[OsmStore]:
    """Fetch stores for a single chain from Overpass API."""
    query = f"""
[out:json][timeout:90];
area["ISO3166-1"="IT"]->.italy;
(
{filter_lines}
);
out center tags qt;
"""
    logger.info("  Querying %s ...", chain_slug)
    response = await client.post(OVERPASS_URL, data={"data": query})
    response.raise_for_status()

    data = response.json()
    if data.get("remark"):
        logger.warning("  %s: Overpass remark: %s", chain_slug, data["remark"])

    elements = data.get("elements", [])
    stores = _parse_elements(elements, chain_slug)
    logger.info("  %s: %d elements → %d stores", chain_slug, len(elements), len(stores))
    return stores


async def fetch_all_stores() -> list[OsmStore]:
    """Fetch stores for all chains sequentially (to respect Overpass rate limits)."""
    all_stores: list[OsmStore] = []

    async with httpx.AsyncClient(timeout=120) as client:
        for chain_slug, filter_lines in CHAIN_QUERIES:
            for attempt in range(3):
                try:
                    stores = await fetch_chain_stores(client, chain_slug, filter_lines)
                    all_stores.extend(stores)
                    break
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 429 and attempt < 2:
                        wait = 30 * (attempt + 1)
                        logger.warning(
                            "  %s: rate-limited, retrying in %ds...",
                            chain_slug, wait,
                        )
                        await asyncio.sleep(wait)
                    else:
                        logger.error("  %s: HTTP error %s", chain_slug, e.response.status_code)
                        break
                except Exception as e:
                    logger.error("  %s: %s", chain_slug, e)
                    break

            # Pause between queries to respect Overpass rate limits
            await asyncio.sleep(12)

    logger.info("Total: %d stores across %d chains.", len(all_stores), len(CHAIN_QUERIES))
    return all_stores


async def import_stores(dry_run: bool = False) -> None:
    """Import OSM stores into the database."""
    from app.database import async_session
    from app.models import Chain

    logger.info("Fetching store locations from OpenStreetMap...")
    stores = await fetch_all_stores()

    if not stores:
        logger.warning("No stores fetched from OSM. Aborting.")
        return

    # Print per-chain summary
    chain_counts = Counter(s.chain_slug for s in stores)
    logger.info("Stores by chain:")
    for slug, count in sorted(chain_counts.items(), key=lambda x: -x[1]):
        logger.info("  %-15s %5d", slug, count)
    logger.info("  %-15s %5d", "TOTAL", len(stores))

    if dry_run:
        logger.info("DRY RUN — no database changes made.")
        return

    async with async_session() as session:
        # Load chain slug → id mapping
        result = await session.execute(select(Chain.id, Chain.slug))
        slug_to_id: dict[str, str] = {row.slug: row.id for row in result.fetchall()}

        skipped_no_chain = 0
        inserted = 0
        updated = 0

        for i in range(0, len(stores), BATCH_SIZE):
            batch = stores[i : i + BATCH_SIZE]
            for store in batch:
                chain_id = slug_to_id.get(store.chain_slug)
                if not chain_id:
                    skipped_no_chain += 1
                    continue

                opening_hours_json = (
                    json.dumps({"raw": store.opening_hours})
                    if store.opening_hours
                    else None
                )

                result = await session.execute(
                    text("""
                        INSERT INTO stores (id, chain_id, osm_id, name, address, city,
                                            province, zip_code, lat, lon, phone,
                                            opening_hours)
                        VALUES (gen_random_uuid(), :chain_id, :osm_id, :name, :address,
                                :city, :province, :zip_code, :lat, :lon, :phone,
                                CAST(:opening_hours AS jsonb))
                        ON CONFLICT (osm_id) DO UPDATE SET
                            name = EXCLUDED.name,
                            address = EXCLUDED.address,
                            city = EXCLUDED.city,
                            province = COALESCE(EXCLUDED.province, stores.province),
                            zip_code = COALESCE(EXCLUDED.zip_code, stores.zip_code),
                            lat = EXCLUDED.lat,
                            lon = EXCLUDED.lon,
                            phone = COALESCE(EXCLUDED.phone, stores.phone),
                            opening_hours = COALESCE(EXCLUDED.opening_hours, stores.opening_hours)
                        RETURNING (xmax = 0) AS is_insert
                    """),
                    {
                        "chain_id": str(chain_id),
                        "osm_id": store.osm_id,
                        "name": store.name,
                        "address": store.address,
                        "city": store.city,
                        "province": store.province or "??",
                        "zip_code": store.zip_code,
                        "lat": store.lat,
                        "lon": store.lon,
                        "phone": store.phone,
                        "opening_hours": opening_hours_json,
                    },
                )
                row = result.fetchone()
                if row and row.is_insert:
                    inserted += 1
                else:
                    updated += 1

            await session.flush()
            logger.info(
                "  Batch %d-%d processed (%d inserted, %d updated so far).",
                i + 1,
                min(i + BATCH_SIZE, len(stores)),
                inserted,
                updated,
            )

        await session.commit()

        logger.info("=" * 50)
        logger.info("Import complete.")
        logger.info("  Inserted: %d", inserted)
        logger.info("  Updated:  %d", updated)
        logger.info("  Skipped (no chain): %d", skipped_no_chain)
        logger.info("=" * 50)


def main():
    parser = argparse.ArgumentParser(
        description="Import supermarket store locations from OpenStreetMap."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and display counts without modifying the database.",
    )
    args = parser.parse_args()
    asyncio.run(import_stores(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
