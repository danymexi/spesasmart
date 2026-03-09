"""SpesaSmart scraping engine.

Exposes all chain scrapers and the shared OCR/AI pipeline.
"""

from app.scrapers.base import BaseScraper
from app.scrapers.carrefour import CarrefourScraper
from app.scrapers.coop import CoopScraper
from app.scrapers.esselunga import EsselungaScraper
from app.scrapers.esselunga_online import EsselungaOnlineScraper
from app.scrapers.eurospin import EurospinScraper
from app.scrapers.iperal import IperalScraper
from app.scrapers.iperal_online import IperalOnlineScraper
from app.scrapers.lidl import LidlScraper
from app.scrapers.pipeline import ScrapingPipeline

__all__ = [
    "BaseScraper",
    "CarrefourScraper",
    "CoopScraper",
    "EsselungaScraper",
    "EsselungaOnlineScraper",
    "EurospinScraper",
    "IperalScraper",
    "IperalOnlineScraper",
    "LidlScraper",
    "ScrapingPipeline",
]

# Registry mapping chain slugs to their scraper classes.
SCRAPER_REGISTRY: dict[str, type[BaseScraper]] = {
    "carrefour": CarrefourScraper,
    "esselunga": EsselungaScraper,
    "eurospin": EurospinScraper,
    "lidl": LidlScraper,
    "coop": CoopScraper,
    "iperal": IperalScraper,
}
