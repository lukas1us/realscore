"""
Unit testy pro backend/services/benchmarks.py

Testuje pouze _normalize_city() — jedinou pure funkci bez DB závislosti.
"""

from backend.services.benchmarks import _normalize_city


class TestNormalizeCity:
    def test_plain_city(self):
        assert _normalize_city("Kyjov") == "Kyjov"

    def test_city_with_district_suffix(self):
        assert _normalize_city("Brno - Žebětín") == "Brno"

    def test_praha_with_district(self):
        assert _normalize_city("Praha 4 - Krč") == "Praha 4"

    def test_city_with_multiple_dashes(self):
        # Pouze první část před " - " se bere
        assert _normalize_city("Frýdek-Místek - Místek") == "Frýdek-Místek"

    def test_none_returns_none(self):
        assert _normalize_city(None) is None

    def test_empty_string_returns_none(self):
        assert _normalize_city("") is None

    def test_whitespace_only_returns_none(self):
        assert _normalize_city("   ") is None

    def test_strips_whitespace(self):
        assert _normalize_city("  Brno  ") == "Brno"
