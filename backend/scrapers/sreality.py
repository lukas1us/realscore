"""
Sreality.cz scraper.

Sreality exposes an internal JSON API:
  https://www.sreality.cz/api/cs/v2/estates/{estate_id}

The estate ID is the last numeric segment of the detail URL, e.g.:
  https://www.sreality.cz/detail/prodej/byt/2+1/Praha/.../12345678
  → estate_id = 12345678
"""

import re
import logging
from functools import lru_cache
from typing import Optional
import httpx

logger = logging.getLogger(__name__)

from backend.scrapers.constants import HEADERS_API as HEADERS, CONSTRUCTION_KEYWORDS, DISP_TO_CODE, parse_ownership

ENERGY_CLASS_MAP = {
    "a": "A", "b": "B", "c": "C", "d": "D",
    "e": "E", "f": "F", "g": "G",
}

_SEO_MAIN = {1: "prodej", 2: "pronajem"}
_SEO_TYPE = {1: "byt", 2: "dum", 3: "pozemek", 4: "komercni", 5: "ostatni"}
_SEO_SUB  = {
    2: "1+kk", 3: "1+1", 4: "2+kk", 5: "2+1",
    6: "3+kk", 7: "3+1", 8: "4+kk", 9: "4+1",
    10: "5+kk", 11: "5+1", 12: "6+",
}


def _canonical_url(seo: dict, estate_id: int) -> Optional[str]:
    """Build the real Sreality web URL from the seo block in the API response."""
    main = _SEO_MAIN.get(seo.get("category_main_cb"))
    typ  = _SEO_TYPE.get(seo.get("category_type_cb"))
    sub  = _SEO_SUB.get(seo.get("category_sub_cb"), "-")
    loc  = seo.get("locality", "-")
    if main and typ and loc:
        return f"https://www.sreality.cz/detail/{main}/{typ}/{sub}/{loc}/{estate_id}"
    return None



def extract_estate_id(url: str) -> Optional[int]:
    """Pull the numeric estate ID from a Sreality detail URL."""
    match = re.search(r"/(\d{5,})", url)
    if match:
        return int(match.group(1))
    return None


def _find_item(items: list[dict], name: str) -> Optional[str]:
    """Search sreality 'items' array for a named field."""
    for item in items:
        if item.get("name", "").lower() == name.lower():
            vals = item.get("value", [])
            if isinstance(vals, list) and vals:
                return str(vals[0])
            if isinstance(vals, str):
                return vals
    return None


def _parse_construction(raw: str) -> str:
    low = raw.lower()
    for kw, canonical in CONSTRUCTION_KEYWORDS.items():
        if kw in low:
            return canonical
    return raw


def scrape_sreality(url: str) -> dict:
    """
    Fetch property data from Sreality JSON API.

    Returns a dict with normalised fields.
    Raises ValueError on failure so callers can fall back to manual input.
    """
    estate_id = extract_estate_id(url)
    if estate_id is None:
        raise ValueError(f"Nepodařilo se extrahovat ID nemovitosti z URL: {url}")

    api_url = f"https://www.sreality.cz/api/cs/v2/estates/{estate_id}"
    logger.info("Fetching Sreality API: %s", api_url)

    with httpx.Client(headers=HEADERS, timeout=15, follow_redirects=True) as client:
        resp = client.get(api_url)

    if resp.status_code != 200:
        raise ValueError(
            f"Sreality API vrátilo status {resp.status_code} pro estate ID {estate_id}"
        )

    data = resp.json()
    logger.debug("Sreality raw keys: %s", list(data.keys()))

    # --- helpers ---
    def _val(field) -> Optional[str]:
        """Extract string value from plain scalar, dict with 'value', or list."""
        if field is None:
            return None
        if isinstance(field, (int, float)):
            return str(field)
        if isinstance(field, str):
            return field
        if isinstance(field, dict):
            v = field.get("value")
            return _val(v)
        if isinstance(field, list) and field:
            return _val(field[0])
        return None

    def _num(field) -> Optional[float]:
        raw = _val(field)
        if raw is None:
            return None
        nums = re.findall(r"[\d]+", raw.replace("\xa0", "").replace(" ", ""))
        return float(nums[0]) if nums else None

    # --- name & locality ---
    name: str = _val(data.get("name")) or ""
    locality: str = _val(data.get("locality")) or ""

    items: list[dict] = data.get("items", [])
    logger.debug("Items: %s", [i.get("name") for i in items])

    # --- price ---
    # "Celková cena" from items is the total price shown on the listing page and
    # the same value Sreality uses for its price_to search filter.  The top-level
    # price_czk field can be a lower base/asking price (without broker commission),
    # which would cause the price-cap post-filter in full_market_scan to miss
    # over-budget listings.  Always prefer items first.
    raw_price_item = _find_item(items, "Celková cena") or _find_item(items, "Cena")
    price_czk: Optional[float] = _num(raw_price_item) if raw_price_item else None
    if price_czk is None:
        price_czk = _num(data.get("price_czk")) or _num(data.get("price"))

    # --- size ---
    size_m2: Optional[float] = None
    raw_size = (
        _find_item(items, "Užitná plocha")
        or _find_item(items, "Plocha")
        or _find_item(items, "Celková plocha")
        or _find_item(items, "Podlahová plocha")
    )
    if raw_size:
        nums = re.findall(r"[\d]+", raw_size.replace("\xa0", "").replace(" ", ""))
        if nums:
            size_m2 = float(nums[0])
    # Last resort: extract m² from title, e.g. "Prodej bytu 1+1, 38 m²"
    if size_m2 is None:
        m = re.search(r"(\d+)\s*m²", name)
        if m:
            size_m2 = float(m.group(1))

    # --- year built ---
    year_built: Optional[int] = None
    raw_year = (
        _find_item(items, "Rok kolaudace")
        or _find_item(items, "Rok výstavby")
        or _find_item(items, "Rok rekonstrukce")
    )
    if raw_year:
        ym = re.search(r"\d{4}", raw_year)
        if ym:
            year_built = int(ym.group())

    # --- floor ---
    floor: Optional[int] = None
    raw_floor = _find_item(items, "Podlaží")
    if raw_floor:
        fm = re.search(r"(\d+)", raw_floor)
        if fm:
            floor = int(fm.group(1))

    # --- energy class ---
    energy_class: Optional[str] = None
    raw_energy = (
        _find_item(items, "Energetická náročnost budovy")
        or _find_item(items, "Energetická třída")
        or _find_item(items, "Energetická náročnost")
    )
    if raw_energy:
        em = re.search(r"\b([A-Ga-g])\b", raw_energy)
        if em:
            energy_class = em.group(1).upper()

    # --- construction ---
    construction_type: Optional[str] = None
    raw_construction = (
        _find_item(items, "Konstrukce budovy")
        or _find_item(items, "Typ budovy")
        or _find_item(items, "Stavba")
    )
    if raw_construction:
        construction_type = _parse_construction(raw_construction)

    # --- elevator ---
    # 1. Check accessories list: {"name": "Příslušenství", "value": ["Výtah", ...]}
    has_elevator: Optional[bool] = None
    for item in items:
        if item.get("name", "").lower() in ("příslušenství", "prislusenstvi", "vybavení"):
            vals = item.get("value", [])
            if isinstance(vals, list):
                if any("výtah" in str(v).lower() for v in vals):
                    has_elevator = True
                    break
    # 2. Check for a standalone boolean/named item "Výtah"
    if has_elevator is None:
        raw_elevator = _find_item(items, "Výtah") or _find_item(items, "Lift")
        if raw_elevator is not None:
            has_elevator = raw_elevator.lower() in ("ano", "yes", "1", "true")
    # 3. Fall back to description text
    if has_elevator is None:
        description: str = _val(data.get("text")) or _val(data.get("description")) or ""
        if re.search(r"výtah", description, re.IGNORECASE):
            has_elevator = True

    # --- ownership ---
    ownership: Optional[str] = None
    raw_ownership = _find_item(items, "Vlastnictví") or _find_item(items, "Vlastnictvi")
    if raw_ownership:
        ownership = parse_ownership(raw_ownership)
    # Sreality sometimes encodes DV_no_transfer only in description text
    if ownership == "DV":
        desc_text = _val(data.get("text")) or _val(data.get("description")) or name
        if re.search(r"bez\s+možnosti\s+převodu|bez\s+prevodu", desc_text, re.IGNORECASE):
            ownership = "DV_no_transfer"

    # --- service charge (fond oprav) ---
    service_charge: Optional[float] = None
    raw_service = (
        _find_item(items, "Poplatek za správu domu a pozemku")
        or _find_item(items, "Fond oprav")
        or _find_item(items, "Náklady na bydlení")
        or _find_item(items, "Náklady na správu domu")
    )
    if raw_service:
        sc_nums = re.findall(r"[\d]+", raw_service.replace("\xa0", "").replace(" ", ""))
        if sc_nums:
            service_charge = float(sc_nums[0])

    # --- disposition from name ---
    disposition: Optional[str] = None
    disp_match = re.search(r"(\d\+(?:kk|\d))", name, re.IGNORECASE)
    if disp_match:
        disposition = disp_match.group(1).lower()

    # --- location ---
    city: Optional[str] = None
    district: Optional[str] = None
    if locality:
        parts = [p.strip() for p in locality.split(",")]
        # Sreality returns locality as "Street/Neighbourhood, City, Region" (3 parts)
        # or "City, Region" (2 parts) or "Praha X" style for Prague.
        # Detect Praha by finding any part starting with "Praha".
        praha_idx = next(
            (i for i, p in enumerate(parts) if re.match(r"^Praha", p, re.IGNORECASE)),
            None,
        )
        if praha_idx is not None and praha_idx > 0:
            # Street/neighbourhood came first; city is the Praha part
            city = "Praha"
            district = parts[praha_idx]  # e.g. "Praha 6"
        elif len(parts) >= 3:
            # "Street, Municipality, Region" — municipality is second-to-last
            city = parts[-2]
            district = parts[-2]  # keep municipality in district for benchmark lookups
        else:
            city = parts[0] if parts else None
            district = parts[1] if len(parts) >= 2 else None

    logger.info(
        "Parsed: price=%s size=%s disposition=%s city=%s",
        price_czk, size_m2, disposition, city,
    )

    seo = data.get("seo") or {}
    canonical = _canonical_url(seo, estate_id)

    return {
        "url": canonical or url,
        "address": locality or None,
        "city": city,
        "district": district,
        "price": price_czk,
        "size_m2": size_m2,
        "disposition": disposition,
        "construction_type": construction_type,
        "energy_class": energy_class,
        "year_built": year_built,
        "floor": floor,
        "has_elevator": has_elevator,
        "ownership": ownership,
        "service_charge": service_charge,
        "raw_data": data,
    }


# ---------------------------------------------------------------------------
# Rental-listing scraper (same city, same disposition)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1024)
def scrape_rental_estimates(city: str, disposition: str, count: int = 20) -> list[float]:
    """
    Search Sreality for rental listings matching city + disposition.
    Returns list of monthly rents (CZK).
    """
    if not city or not disposition:
        return []

    sub_cb = DISP_TO_CODE.get(disposition.lower())

    params: dict = {
        "category_main_cb": 2,   # pronájem
        "category_type_cb": 1,   # byt
        "per_page": count,
        "page": 1,
        "locality_region_id": 0,
    }
    if sub_cb:
        params["category_sub_cb"] = sub_cb

    # Sreality search API
    search_url = "https://www.sreality.cz/api/cs/v2/estates"
    try:
        with httpx.Client(headers=HEADERS, timeout=15) as client:
            resp = client.get(search_url, params=params)
        if resp.status_code != 200:
            logger.warning("Rental search returned %s", resp.status_code)
            return []
        results = resp.json().get("_embedded", {}).get("estates", [])
        rents = []
        for estate in results:
            p = estate.get("price")
            if p and isinstance(p, (int, float)) and p > 1000:
                rents.append(float(p))
        return rents
    except Exception as exc:
        logger.warning("Rental scrape failed: %s", exc)
        return []
