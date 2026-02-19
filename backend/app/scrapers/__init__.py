"""SpesaSmart scraping engine.

Exposes all chain scrapers and the shared OCR/AI pipeline.
"""

from app.scrapers.base import BaseScraper
from app.scrapers.coop import CoopScraper
from app.scrapers.esselunga import EsselungaScraper
from app.scrapers.iperal import IperalScraper
from app.scrapers.lidl import LidlScraper
from app.scrapers.pipeline import ScrapingPipeline

__all__ = [
    "BaseScraper",
    "CoopScraper",
    "EsselungaScraper",
    "IperalScraper",
    "LidlScraper",
    "ScrapingPipeline",
]

# Registry mapping chain slugs to their scraper classes.
SCRAPER_REGISTRY: dict[str, type[BaseScraper]] = {
    "esselunga": EsselungaScraper,
    "lidl": LidlScraper,
    "coop": CoopScraper,
    "iperal": IperalScraper,
}
