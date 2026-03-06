"""Celery task for syncing product data to Meilisearch."""

import logging

import meilisearch

from config import settings
from tasks import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="tasks.search_sync.sync_search_index")
def sync_search_index():
    """Sync canonical_products to Meilisearch index."""
    logger.info("Starting Meilisearch sync")

    client = meilisearch.Client(settings.meilisearch_host, settings.meilisearch_api_key)

    # Configure index settings
    index = client.index("products")
    index.update_settings({
        "searchableAttributes": ["name", "brand", "tags", "category_name"],
        "filterableAttributes": [
            "category_id", "available_chain_ids", "has_discount", "quantity_unit"
        ],
        "sortableAttributes": ["name", "min_price", "discount_percent"],
        "typoTolerance": {
            "enabled": True,
            "minWordSizeForTypos": {"oneTypo": 4, "twoTypos": 8},
        },
        "synonyms": {
            "latte": ["milk"],
            "olio": ["olio d'oliva", "olio extravergine"],
            "pasta": ["spaghetti", "penne", "rigatoni", "fusilli"],
            "biscotti": ["frollini", "cookies"],
            "yogurt": ["yog"],
            "detersivo": ["detergente"],
            "carta igienica": ["carta bagno", "rotoli"],
        },
    })

    logger.info("Meilisearch index settings updated")
    # Full data sync will query DB and push documents
    # For now, this is a placeholder
    return {"status": "completed"}
