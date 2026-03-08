"""Import store locations directly from chain websites.

Supplements the OSM import with official data from chains that have
poor OSM coverage. Currently supports:
- Eurospin (~1260 stores) — scrapes embedded JS from /punti-vendita/
- Penny Market (~450 stores) — public JSON API at /api/stores
- Aldi (~190 stores) — crawls sitemap + JSON-LD from individual pages

These stores use a negative synthetic osm_id (chain-specific offset)
to avoid conflicts with real OSM IDs while still supporting upsert.

Run from the backend directory:
    docker compose exec backend python -m app.scripts.import_chain_stores
    docker compose exec backend python -m app.scripts.import_chain_stores --dry-run
    docker compose exec backend python -m app.scripts.import_chain_stores --chain eurospin
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
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

BATCH_SIZE = 200

# Synthetic osm_id offsets per chain (negative, to avoid OSM conflicts)
EUROSPIN_OFFSET = -9_000_000
PENNY_OFFSET = -8_000_000
ALDI_OFFSET = -7_000_000


@dataclass
class ChainStore:
    """Parsed store data from a chain website."""
    synthetic_id: int  # used as osm_id for upsert
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


# ─── Eurospin ─────────────────────────────────────────────────────────────────

async def fetch_eurospin(client: httpx.AsyncClient) -> list[ChainStore]:
    """Parse Eurospin stores from embedded JS variable on /punti-vendita/."""
    logger.info("  Fetching Eurospin /punti-vendita/ ...")
    resp = await client.get(
        "https://www.eurospin.it/punti-vendita/",
        headers={"User-Agent": "SpesaSmart/1.0 store-importer"},
    )
    resp.raise_for_status()
    html = resp.text

    # Extract var stores = [...];
    match = re.search(r"var\s+stores\s*=\s*(\[.*?\])\s*;", html, re.DOTALL)
    if not match:
        logger.error("  Eurospin: could not find 'var stores' in HTML")
        return []

    raw = match.group(1)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Sometimes trailing commas — try fixing
        cleaned = re.sub(r",\s*([}\]])", r"\1", raw)
        data = json.loads(cleaned)

    stores: list[ChainStore] = []
    for i, item in enumerate(data):
        lat = item.get("lat", 0)
        lng = item.get("lng", 0)
        if not lat or not lng or (lat == 0 and lng == 0):
            continue

        # Parse address from HTML content: "Via Example 1<br>City Province, 12345"
        content = item.get("content", "")
        address, city, province, zip_code = None, None, None, None
        if content:
            parts = re.split(r"<br\s*/?>", content)
            if parts:
                address = re.sub(r"<[^>]+>", "", parts[0]).strip() or None
            if len(parts) > 1:
                location_line = re.sub(r"<[^>]+>", "", parts[1]).strip()
                # Pattern: "City Province, ZIP" or "City, ZIP"
                loc_match = re.match(
                    r"^(.+?)\s*,\s*(\d{5})\s*$", location_line
                )
                if loc_match:
                    city_prov = loc_match.group(1).strip()
                    zip_code = loc_match.group(2)
                    # Try to split "City Province" (Province is usually 2-letter code at end)
                    prov_match = re.match(
                        r"^(.+?)\s+([A-Z]{2})$", city_prov
                    )
                    if prov_match:
                        city = prov_match.group(1).strip()
                        province = prov_match.group(2)
                    else:
                        city = city_prov
                else:
                    city = location_line or None

        name = item.get("name", "").strip()
        if name:
            name = f"Eurospin {name}"
        else:
            name = f"Eurospin {city}" if city else "Eurospin"

        # Skip invalid coordinates (lat must be -90..90, lon -180..180)
        if abs(lat) > 90 or abs(lng) > 180:
            continue

        stores.append(ChainStore(
            synthetic_id=EUROSPIN_OFFSET - i,
            chain_slug="eurospin",
            name=name[:200],
            address=address,
            city=city[:100] if city else None,
            province=province[:10] if province else None,
            zip_code=zip_code[:10] if zip_code else None,
            lat=round(lat, 7),
            lon=round(lng, 7),
            phone=None,
            opening_hours=None,
        ))

    logger.info("  Eurospin: %d stores parsed", len(stores))
    return stores


# ─── Penny Market ─────────────────────────────────────────────────────────────

async def fetch_penny(client: httpx.AsyncClient) -> list[ChainStore]:
    """Fetch Penny Market stores from public JSON API."""
    logger.info("  Fetching Penny /api/stores ...")
    resp = await client.get(
        "https://www.penny.it/api/stores",
        headers={"User-Agent": "SpesaSmart/1.0 store-importer"},
    )
    resp.raise_for_status()
    data = resp.json()

    stores: list[ChainStore] = []
    for i, item in enumerate(data):
        pos = item.get("position", {})
        lat = pos.get("lat", 0)
        lng = pos.get("lng", 0)
        if not lat or not lng or abs(lat) > 90 or abs(lng) > 180:
            continue

        city = item.get("city", "")
        store_id = item.get("storeId", "")
        # Extract numeric part from "#1-30155" format
        id_num = re.search(r"\d+$", store_id)
        sid = int(id_num.group()) if id_num else i

        name = f"Penny {city}" if city else "Penny Market"

        # Parse opening hours
        opening_times = item.get("openingTimes")
        oh_str = None
        if opening_times:
            parts = []
            for day_info in opening_times:
                dow = day_info.get("dayOfWeek", "")
                times = day_info.get("times", [])
                if len(times) == 2:
                    parts.append(f"{dow} {times[0]}-{times[1]}")
                elif len(times) == 4:
                    parts.append(f"{dow} {times[0]}-{times[1]}, {times[2]}-{times[3]}")
            oh_str = "; ".join(parts) if parts else None

        stores.append(ChainStore(
            synthetic_id=PENNY_OFFSET - sid,
            chain_slug="penny",
            name=name[:200],
            address=item.get("street", "")[:200] or None,
            city=city[:100] or None,
            province=None,  # Penny's "province" field is the region, not province code
            zip_code=(item.get("zip") or "")[:10] or None,
            lat=round(lat, 7),
            lon=round(lng, 7),
            phone=None,
            opening_hours=oh_str,
        ))

    logger.info("  Penny: %d stores parsed", len(stores))
    return stores


# ─── Aldi ─────────────────────────────────────────────────────────────────────

async def fetch_aldi(client: httpx.AsyncClient) -> list[ChainStore]:
    """Crawl Aldi store pages from sitemap and extract JSON-LD data."""
    logger.info("  Fetching Aldi sitemap ...")
    resp = await client.get(
        "https://www.aldi.it/sitemap.xml",
        headers={"User-Agent": "SpesaSmart/1.0 store-importer"},
    )
    resp.raise_for_status()
    sitemap_xml = resp.text

    # Find all store page URLs: /it/trova-il-punto-vendita/aldi-{prov}/aldi-{name}.html
    store_urls = re.findall(
        r"<loc>(https://www\.aldi\.it/it/trova-il-punto-vendita/aldi-[^/]+/aldi-[^<]+\.html)</loc>",
        sitemap_xml,
    )
    logger.info("  Aldi: found %d store pages in sitemap", len(store_urls))

    stores: list[ChainStore] = []
    # Process in batches to avoid hammering the server
    semaphore = asyncio.Semaphore(5)

    async def fetch_store_page(url: str, idx: int) -> ChainStore | None:
        async with semaphore:
            try:
                r = await client.get(
                    url,
                    headers={"User-Agent": "SpesaSmart/1.0 store-importer"},
                )
                r.raise_for_status()
            except Exception as e:
                logger.warning("  Aldi: failed to fetch %s: %s", url, e)
                return None

            # Extract all JSON-LD blocks and find LocalBusiness
            ld_blocks = re.findall(
                r'<script\s+type="application/ld\+json"\s*>(.*?)</script>',
                r.text,
                re.DOTALL,
            )
            ld = None
            for block in ld_blocks:
                try:
                    parsed = json.loads(block)
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed, list):
                    for item in parsed:
                        if isinstance(item, dict) and item.get("@type") == "LocalBusiness":
                            ld = item
                            break
                elif isinstance(parsed, dict) and parsed.get("@type") == "LocalBusiness":
                    ld = parsed
                if ld:
                    break
            if not ld:
                return None

            geo = ld.get("geo", {})
            lat = geo.get("latitude")
            lon = geo.get("longitude")
            if not lat or not lon:
                return None

            addr = ld.get("address", {})
            city = addr.get("addressLocality", "")
            street = addr.get("streetAddress", "")
            zip_code = addr.get("postalCode", "")
            name = ld.get("name", "").strip() or f"Aldi {city}"
            phone = ld.get("telephone", "")

            # Parse opening hours
            oh_specs = ld.get("openingHoursSpecification", [])
            oh_parts = []
            for spec in oh_specs:
                days = spec.get("dayOfWeek", [])
                if isinstance(days, str):
                    days = [days]
                opens = spec.get("opens", "")
                closes = spec.get("closes", "")
                if opens and closes:
                    day_str = ",".join(d[:3] for d in days)
                    oh_parts.append(f"{day_str} {opens}-{closes}")
            oh_str = "; ".join(oh_parts) if oh_parts else None

            return ChainStore(
                synthetic_id=ALDI_OFFSET - idx,
                chain_slug="aldi",
                name=name[:200],
                address=street[:200] or None,
                city=city[:100] or None,
                province=None,
                zip_code=zip_code[:10] or None,
                lat=round(float(lat), 7),
                lon=round(float(lon), 7),
                phone=phone[:30] or None,
                opening_hours=oh_str,
            )

    tasks = [fetch_store_page(url, i) for i, url in enumerate(store_urls)]
    results = await asyncio.gather(*tasks)
    stores = [s for s in results if s is not None]

    logger.info("  Aldi: %d stores parsed (of %d pages)", len(stores), len(store_urls))
    return stores


# ─── Import logic (shared with import_osm_stores.py) ─────────────────────────

CHAIN_FETCHERS: dict[str, any] = {
    "eurospin": fetch_eurospin,
    "penny": fetch_penny,
    "aldi": fetch_aldi,
}


async def import_chain_stores(
    dry_run: bool = False,
    chains: list[str] | None = None,
) -> None:
    """Import stores from chain websites into the database."""
    from app.database import async_session
    from app.models import Chain

    targets = chains or list(CHAIN_FETCHERS.keys())
    logger.info("Fetching store locations from chain websites: %s", ", ".join(targets))

    all_stores: list[ChainStore] = []
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        for slug in targets:
            fetcher = CHAIN_FETCHERS.get(slug)
            if not fetcher:
                logger.warning("Unknown chain: %s", slug)
                continue
            try:
                stores = await fetcher(client)
                all_stores.extend(stores)
            except Exception as e:
                logger.error("  %s: fetch failed: %s", slug, e)

    if not all_stores:
        logger.warning("No stores fetched. Aborting.")
        return

    # Summary
    chain_counts = Counter(s.chain_slug for s in all_stores)
    logger.info("Stores by chain:")
    for slug, count in sorted(chain_counts.items(), key=lambda x: -x[1]):
        logger.info("  %-15s %5d", slug, count)
    logger.info("  %-15s %5d", "TOTAL", len(all_stores))

    if dry_run:
        logger.info("DRY RUN — no database changes made.")
        return

    async with async_session() as session:
        result = await session.execute(select(Chain.id, Chain.slug))
        slug_to_id: dict[str, str] = {row.slug: row.id for row in result.fetchall()}

        skipped = 0
        inserted = 0
        updated = 0

        errors = 0
        for i in range(0, len(all_stores), BATCH_SIZE):
            batch = all_stores[i : i + BATCH_SIZE]
            for store in batch:
                chain_id = slug_to_id.get(store.chain_slug)
                if not chain_id:
                    skipped += 1
                    continue

                # Extra guard: skip out-of-range coordinates
                if abs(store.lat) > 90 or abs(store.lon) > 180:
                    skipped += 1
                    continue

                opening_hours_json = (
                    json.dumps({"raw": store.opening_hours})
                    if store.opening_hours
                    else None
                )

                try:
                    res = await session.execute(
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
                                city = COALESCE(EXCLUDED.city, stores.city),
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
                            "osm_id": store.synthetic_id,
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
                    row = res.fetchone()
                    if row and row.is_insert:
                        inserted += 1
                    else:
                        updated += 1
                except Exception as e:
                    errors += 1
                    logger.warning("  Skipped store %s: %s", store.name, e)
                    # Rollback the failed statement so the session stays usable
                    await session.rollback()

            await session.flush()
            logger.info(
                "  Batch %d-%d processed (%d inserted, %d updated, %d errors so far).",
                i + 1,
                min(i + BATCH_SIZE, len(all_stores)),
                inserted,
                updated,
                errors,
            )

        await session.commit()

        logger.info("=" * 50)
        logger.info("Import complete.")
        logger.info("  Inserted: %d", inserted)
        logger.info("  Updated:  %d", updated)
        logger.info("  Skipped:  %d", skipped)
        logger.info("  Errors:   %d", errors)
        logger.info("=" * 50)


def main():
    parser = argparse.ArgumentParser(
        description="Import store locations from chain websites (Eurospin, Penny, Aldi)."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and display counts without modifying the database.",
    )
    parser.add_argument(
        "--chain",
        choices=list(CHAIN_FETCHERS.keys()),
        help="Import only a specific chain.",
    )
    args = parser.parse_args()
    chains = [args.chain] if args.chain else None
    asyncio.run(import_chain_stores(dry_run=args.dry_run, chains=chains))


if __name__ == "__main__":
    main()
