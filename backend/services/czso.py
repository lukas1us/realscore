"""
ČSÚ (Český statistický úřad) data fetcher.

Uses two data sources:
1. CZSO REST API v1 (csudi) for population by municipality.
2. CZSO open-data CSV exports for unemployment / wages by district.

All results are cached in-process (functools.lru_cache) to avoid
hammering the public API during scoring.
"""

import csv
import io
import logging
import re
from functools import lru_cache
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# NOTE: The old CZSO REST API (api.czso.cz/csudi/rest) has been decommissioned –
# DNS no longer resolves.  The replacement is DataStat (data.csu.gov.cz), which uses
# a completely different POST-based API and is not yet integrated here.
#
# TODO: rewrite czso.py to use the DataStat API (https://data.csu.gov.cz).
#   Key docs: https://csu.gov.cz/zakladni-informace-pro-pouziti-api-datastatu
#   Unemployment dataset code: WADMUPCRMC (regional level; district-level TBD)
#   Wages dataset: search the catalog at https://data.csu.gov.cz/api/katalog/v1/sady
#
# TODO: both open-data resource URLs below return 404 – CZSO reorganised their
# open-data catalogue and the resource UUIDs changed.  To fix, visit
# https://data.czso.cz/dataset/110080 (unemployment) and
# https://data.czso.cz/dataset/110024 (wages), locate the current resource UUID,
# and update the constants below.
#
# Until both TODOs are resolved, _fetch_unemployment() and _fetch_avg_wage() return
# the national-average fallbacks (3.5 % unemployment, 45 000 CZK wage) and
# score_economic defaults to 50 for all districts.
# Unemployment by district – quarterly table
UNEMPLOYMENT_DATASET_URL = (
    "https://data.czso.cz/api/publish/v1/dataset/"
    "110080/resource/66e3de9b-b54d-48d1-b0fb-37ea8a8b4c81/data"
)

# Average wages by district (annual)
WAGES_DATASET_URL = (
    "https://data.czso.cz/api/publish/v1/dataset/"
    "110024/resource/f11b5929-a1a7-4a91-91bc-8b6dcee5e44b/data"
)

HEADERS = {
    "User-Agent": "RealScoreCZ/1.0 (+https://github.com/yourhandle/realscoreCZ)",
    "Accept": "application/json",
}

HTTP_TIMEOUT = 20


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fetch_csv(url: str) -> list[dict]:
    with httpx.Client(headers=HEADERS, timeout=HTTP_TIMEOUT) as client:
        resp = client.get(url)
    resp.raise_for_status()
    reader = csv.DictReader(io.StringIO(resp.text))
    return list(reader)


# ---------------------------------------------------------------------------
# Population trend (municipality level)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=512)
def get_population_trend(municipality_name: str) -> dict:
    """
    Return population trend data for a municipality.

    Uses the CZSO REST API /data endpoint for the MOS dataset
    (Počet obyvatel v obcích).

    Returns:
        {
            "municipality": str,
            "population_latest": int | None,
            "population_5y_ago": int | None,
            "change_pct": float | None,   # positive = growth
        }
    """
    return _population_from_opendata(municipality_name)


def _population_from_opendata(municipality_name: str) -> dict:
    """Fallback: query CZSO open-data CSV for population."""
    result = {
        "municipality": municipality_name,
        "population_latest": None,
        "population_5y_ago": None,
        "change_pct": None,
    }
    try:
        url = (
            "https://data.czso.cz/api/publish/v1/dataset/"
            "130142/resource/0bf0b3b1-efa6-4a8e-85da-70e99a9b1ede/data"
        )
        rows = _fetch_csv(url)
        # Filter by municipality name (case-insensitive partial match)
        name_low = municipality_name.lower()
        matched = [
            r for r in rows
            if name_low in r.get("uzemi_txt", "").lower()
            or name_low in r.get("obec_txt", "").lower()
        ]
        if not matched:
            return result

        # Pick rows and sort by year
        years: dict[int, int] = {}
        for row in matched:
            yr = _safe_int(row.get("rok") or row.get("casref_txt", "")[:4])
            val = _safe_int(row.get("hodnota") or row.get("pocet_obyvatel"))
            if yr and val:
                years[yr] = val

        if not years:
            return result

        sorted_years = sorted(years.keys(), reverse=True)
        latest_yr = sorted_years[0]
        result["population_latest"] = years[latest_yr]

        target_5y = latest_yr - 5
        # Find closest year to 5 years ago
        closest = min(sorted_years, key=lambda y: abs(y - target_5y))
        if abs(closest - target_5y) <= 2:
            result["population_5y_ago"] = years[closest]
            if result["population_5y_ago"] and result["population_5y_ago"] > 0:
                result["change_pct"] = (
                    (result["population_latest"] - result["population_5y_ago"])
                    / result["population_5y_ago"]
                    * 100
                )

    except Exception as exc:
        logger.warning("Population open-data fallback failed: %s", exc)

    return result


# ---------------------------------------------------------------------------
# Unemployment & wages (district level)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=256)
def get_economic_indicators(district: str) -> dict:
    """
    Return unemployment rate and average wage for a district.

    Returns:
        {
            "district": str,
            "unemployment_pct": float | None,
            "avg_wage_czk": float | None,
        }
    """
    result: dict = {
        "district": district,
        "unemployment_pct": None,
        "avg_wage_czk": None,
    }
    result["unemployment_pct"] = _fetch_unemployment(district)
    result["avg_wage_czk"] = _fetch_avg_wage(district)
    return result


def _fetch_unemployment(district: str) -> Optional[float]:
    """
    Fetch unemployment rate for district from CZSO open-data.
    Dataset: Obecná míra nezaměstnanosti v krajích a okresech.
    """
    # Open-data CSV (URL may be stale – see TODO at the top of this file)
    try:
        rows = _fetch_csv(UNEMPLOYMENT_DATASET_URL)
        district_low = district.lower()
        matched = [
            r for r in rows
            if district_low in r.get("uzemi_txt", "").lower()
            or district_low in r.get("okres_txt", "").lower()
        ]
        if matched:
            # Sort by period descending
            matched_sorted = sorted(
                matched,
                key=lambda r: r.get("casref_txt", r.get("rok", "")),
                reverse=True
            )
            for row in matched_sorted:
                val = _safe_float(
                    row.get("hodnota") or row.get("mira_nezamestnanosti")
                )
                if val is not None:
                    return val
    except Exception as exc:
        logger.warning("Unemployment fetch failed for %s: %s", district, exc)

    # Return Czech national average as last resort
    return 3.5  # CZ average ~3.5% (2024)


def _fetch_avg_wage(district: str) -> Optional[float]:
    """
    Fetch average nominal monthly wage for district.
    Falls back to national average (45 000 CZK) if not found.
    """
    # Open-data CSV (URL may be stale – see TODO at the top of this file)
    try:
        rows = _fetch_csv(WAGES_DATASET_URL)
        district_low = district.lower()
        matched = [
            r for r in rows
            if district_low in r.get("uzemi_txt", "").lower()
            or district_low in r.get("okres_txt", "").lower()
        ]
        if matched:
            matched_sorted = sorted(
                matched,
                key=lambda r: r.get("casref_txt", r.get("rok", "")),
                reverse=True
            )
            for row in matched_sorted:
                val = _safe_float(row.get("hodnota") or row.get("prumerna_mzda"))
                if val is not None:
                    return val
    except Exception as exc:
        logger.warning("Wages fetch failed for %s: %s", district, exc)

    return 45_000.0  # national fallback


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _safe_int(v) -> Optional[int]:
    try:
        return int(str(v).replace(" ", "").replace("\xa0", "").replace(",", ""))
    except (TypeError, ValueError):
        return None


def _safe_float(v) -> Optional[float]:
    try:
        return float(str(v).replace(" ", "").replace("\xa0", "").replace(",", "."))
    except (TypeError, ValueError):
        return None
