"""Tests for product matcher service."""

import pytest

from app.services.product_matcher import ProductMatcher


class TestProductMatcher:
    def setup_method(self):
        self.matcher = ProductMatcher()

    def test_normalize_text(self):
        assert self.matcher.normalize_text("Latte Granarolo PS 1L") == "latte granarolo ps 1l"
        assert self.matcher.normalize_text("  Extra  Spaces  ") == "extra spaces"

    def test_fuzzy_match_identical(self):
        score = self.matcher.fuzzy_match(
            "Latte Granarolo PS 1L",
            "Latte Granarolo PS 1L",
        )
        assert score == 100.0

    def test_fuzzy_match_similar(self):
        score = self.matcher.fuzzy_match(
            "Latte Granarolo PS 1L",
            "GRANAROLO Latte Parz. Scremato 1 litro",
        )
        # Should have reasonable similarity
        assert score > 40

    def test_fuzzy_match_different(self):
        score = self.matcher.fuzzy_match(
            "Latte Granarolo PS 1L",
            "Coca Cola 1.5L",
        )
        assert score < 50

    def test_extract_brand(self):
        brand = self.matcher.extract_brand("Latte Granarolo Parzialmente Scremato")
        assert brand == "Granarolo"

    def test_extract_brand_unknown(self):
        brand = self.matcher.extract_brand("Latte fresco generico")
        assert brand is None

    def test_normalize_unit(self):
        assert self.matcher.normalize_unit("1 litro") == "1l"
        assert self.matcher.normalize_unit("500 grammi") == "500g"
        assert self.matcher.normalize_unit("1,5 kg") == "1.5kg"
