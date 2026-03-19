"""
Market liquidity helper: counts active listings in a locality.
Uses Sreality search API as a proxy for overall activity.
"""

import logging
from typing import Optional
import httpx

logger = logging.getLogger(__name__)

from backend.scrapers.constants import HEADERS_API as HEADERS


def count_active_listings(city: str) -> int:
    """
    Return the total number of sale listings (byty) in the city.
    Uses Sreality search with locality search string.
    Returns 0 on failure.
    """
    if not city:
        return 0

    params = {
        "category_main_cb": 1,  # prodej
        "category_type_cb": 1,  # byt
        "per_page": 1,
        "page": 1,
        "locality_region_id": 0,
        "locality_district_id": 0,
    }
    # Simple text filter – sreality ignores unknown params gracefully
    params["locality"] = city

    try:
        with httpx.Client(headers=HEADERS, timeout=10) as client:
            resp = client.get("https://www.sreality.cz/api/cs/v2/estates", params=params)
        if resp.status_code == 200:
            data = resp.json()
            return int(data.get("result_size", 0))
    except Exception as exc:
        logger.warning("Listing count failed for %s: %s", city, exc)
    return 0
