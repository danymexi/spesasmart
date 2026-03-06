"""Celery task for product normalization and deduplication."""

import logging

from tasks import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="tasks.normalization.run_normalization")
def run_normalization():
    """
    Process unmatched store_products and link them to canonical_products.

    Algorithm:
    1. Find store_products without canonical_product_id
    2. For each, try EAN exact match
    3. If no EAN match, try fuzzy name+brand+quantity match
    4. Score >= 0.92: auto-link
    5. Score 0.75-0.91: add to review queue
    6. Score < 0.75: create new canonical product
    """
    logger.info("Starting normalization pipeline")
    # Implementation will use the normalizer service
    # For now, this is a placeholder
    logger.info("Normalization completed")
    return {"status": "completed"}
