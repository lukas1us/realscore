"""
Unit testy pro backend/utils/regions.py

Pokrývá 5-krokový fallback řetěz extract_kraj() a jednoduchou city_to_kraj().
"""

import pytest
from backend.utils.regions import extract_kraj, city_to_kraj, CZECH_REGIONS, CITY_TO_REGION


# ---------------------------------------------------------------------------
# city_to_kraj
# ---------------------------------------------------------------------------

class TestCityToKraj:
    def test_known_city(self):
        assert city_to_kraj("Brno") == "Jihomoravský kraj"
        assert city_to_kraj("Praha") == "Hlavní město Praha"
        assert city_to_kraj("Ostrava") == "Moravskoslezský kraj"

    def test_unknown_city_returns_none(self):
        assert city_to_kraj("Neexistující město") is None

    def test_none_returns_none(self):
        assert city_to_kraj(None) is None

    def test_empty_string_returns_none(self):
        assert city_to_kraj("") is None


# ---------------------------------------------------------------------------
# extract_kraj — step 1: přímý hit v city
# ---------------------------------------------------------------------------

class TestExtractKrajCityDirect:
    def test_city_direct_match(self):
        assert extract_kraj("Brno", None) == "Jihomoravský kraj"

    def test_city_plzen(self):
        assert extract_kraj("Plzeň", None) == "Plzeňský kraj"

    def test_city_ceske_budejovice(self):
        assert extract_kraj("České Budějovice", None) == "Jihočeský kraj"


# ---------------------------------------------------------------------------
# extract_kraj — step 2: Praha* pattern v city
# ---------------------------------------------------------------------------

class TestExtractKrajPrahaInCity:
    def test_praha_exact(self):
        assert extract_kraj("Praha", None) == "Hlavní město Praha"

    def test_praha_with_number(self):
        assert extract_kraj("Praha 9", None) == "Hlavní město Praha"

    def test_praha_with_district(self):
        # "Praha 6 - Břevnov" → step 2 (Praha v city)
        assert extract_kraj("Praha 6 - Břevnov", None) == "Hlavní město Praha"

    def test_praha_case_insensitive(self):
        assert extract_kraj("praha", None) == "Hlavní město Praha"


# ---------------------------------------------------------------------------
# extract_kraj — step 3: přímý hit v district
# ---------------------------------------------------------------------------

class TestExtractKrajDistrictDirect:
    def test_district_direct_match(self):
        # city je ulice, district je reálné město
        assert extract_kraj("Lidická", "Kyjov") == "Jihomoravský kraj"

    def test_district_brno(self):
        assert extract_kraj("Náměstí Svobody", "Brno") == "Jihomoravský kraj"

    def test_district_ostrava(self):
        assert extract_kraj("Hlavní třída", "Ostrava") == "Moravskoslezský kraj"


# ---------------------------------------------------------------------------
# extract_kraj — step 4: Praha* pattern v district
# ---------------------------------------------------------------------------

class TestExtractKrajPrahaInDistrict:
    def test_praha_in_district(self):
        assert extract_kraj("Italská", "Praha 4") == "Hlavní město Praha"

    def test_praha2_in_district(self):
        assert extract_kraj("Neznámá", "Praha 2") == "Hlavní město Praha"


# ---------------------------------------------------------------------------
# extract_kraj — step 5: "Město - Čtvrť" split v district
# ---------------------------------------------------------------------------

class TestExtractKrajDistrictSplit:
    def test_brno_zebetin(self):
        assert extract_kraj("Ulice", "Brno - Žebětín") == "Jihomoravský kraj"

    def test_olomouc_povel(self):
        assert extract_kraj("Ulice", "Olomouc - Povel") == "Olomoucký kraj"

    def test_plzen_doubravka(self):
        assert extract_kraj("Ulice", "Plzeň - Doubravka") == "Plzeňský kraj"

    def test_ceske_budejovice_with_part(self):
        assert extract_kraj("Ulice", "České Budějovice - Suché Vrbné") == "Jihočeský kraj"


# ---------------------------------------------------------------------------
# extract_kraj — step 6: "okres Xxx" prefix stripping
# ---------------------------------------------------------------------------

class TestExtractKrajOkresPrefix:
    def test_okres_prachatice(self):
        assert extract_kraj(None, "okres Prachatice") == "Jihočeský kraj"

    def test_okres_kyjov(self):
        assert extract_kraj(None, "okres Kyjov") == "Jihomoravský kraj"

    def test_okres_case_insensitive(self):
        assert extract_kraj(None, "Okres Brno") == "Jihomoravský kraj"


# ---------------------------------------------------------------------------
# extract_kraj — neznámé vstupy
# ---------------------------------------------------------------------------

class TestExtractKrajUnknown:
    def test_both_none(self):
        assert extract_kraj(None, None) is None

    def test_unknown_city_and_district(self):
        assert extract_kraj("Neexistující", "Taky neexistující") is None

    def test_empty_strings(self):
        assert extract_kraj("", "") is None


# ---------------------------------------------------------------------------
# Integritní testy dat
# ---------------------------------------------------------------------------

class TestRegionsData:
    def test_czech_regions_count(self):
        assert len(CZECH_REGIONS) == 14

    def test_city_to_region_is_not_empty(self):
        assert len(CITY_TO_REGION) > 100

    def test_all_mapped_cities_point_to_valid_regions(self):
        for city, region in CITY_TO_REGION.items():
            assert region in CZECH_REGIONS, f"{city} → {region} není validní kraj"
