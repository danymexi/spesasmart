"""Tests for scraper components."""

import json

import pytest

from app.scrapers.pipeline import OCRPipeline


class TestOCRPipeline:
    def setup_method(self):
        self.pipeline = OCRPipeline()

    def test_parse_italian_price(self):
        assert self.pipeline.parse_italian_price("1,29") == 1.29
        assert self.pipeline.parse_italian_price("€ 2,50") == 2.50
        assert self.pipeline.parse_italian_price("10,00€") == 10.00
        assert self.pipeline.parse_italian_price("0,89") == 0.89

    def test_parse_italian_price_invalid(self):
        assert self.pipeline.parse_italian_price("") is None
        assert self.pipeline.parse_italian_price("abc") is None

    def test_validate_product_data(self):
        valid = {
            "name": "Latte Granarolo",
            "offer_price": 1.29,
        }
        assert self.pipeline.validate_product_data(valid) is True

        invalid_no_name = {"offer_price": 1.29}
        assert self.pipeline.validate_product_data(invalid_no_name) is False

        invalid_no_price = {"name": "Latte"}
        assert self.pipeline.validate_product_data(invalid_no_price) is False

    def test_clean_product_name(self):
        assert self.pipeline.clean_product_name("  LATTE GRANAROLO  ") == "Latte Granarolo"
        assert self.pipeline.clean_product_name("latte\ngranarolo") == "Latte Granarolo"


class TestScraperHelpers:
    """Test scraper utility functions."""

    def test_normalize_price_string(self):
        from app.scrapers.base import BaseScraper

        assert BaseScraper.normalize_price("1,29") == 1.29
        assert BaseScraper.normalize_price("€1.29") == 1.29
        assert BaseScraper.normalize_price("2,50 €") == 2.50
