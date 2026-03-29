"""Tests for rent_market_scan city → region normalization."""

from backend.jobs.rent_market_scan import _city_to_region_id, _normalize_city_for_region


class TestNormalizeCityForRegion:
    def test_strips_district_suffix(self):
        assert _normalize_city_for_region("Brno - Černá Pole") == "Brno"

    def test_praha_district_maps_to_praha(self):
        assert _normalize_city_for_region("Praha 4 - Krč") == "praha"

    def test_plain_city(self):
        assert _normalize_city_for_region("Olomouc") == "Olomouc"


class TestCityToRegionId:
    def test_brno_district_resolves(self):
        assert _city_to_region_id("Brno - Černá Pole") == 14

    def test_praha_district_resolves(self):
        assert _city_to_region_id("Praha 8") == 10
        assert _city_to_region_id("Praha 3 - Vinohrady") == 10

    def test_unknown_returns_none(self):
        assert _city_to_region_id("Neexistující Vesnice XYZ") is None
