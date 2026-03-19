"""
Sreality search-page scraper.

Converts a Sreality UI search URL into API parameters, paginates through
all result pages, then full-scrapes each estate detail.

Flow:
  parse_search_url(url)  →  (api_params, bbox)
  collect_estate_ids()   →  list of estate_ids (GPS-filtered if bbox present)
  full_scrape_search()   →  list of property dicts

Geographic filtering strategy
──────────────────────────────
The Sreality /api/cs/v2/estates endpoint ignores bounding-box (lat/lon)
query params entirely.  Instead we use a two-stage approach:

  1. locality_region_id  – maps the city/region slug in the URL path to one of
     Sreality's 14 internal region IDs so the API pre-filters to the right
     region (~1 000 results instead of ~15 000 nationwide).

  2. GPS post-filter     – each estate in the search-result list carries a
     {"lat": …, "lon": …} gps field.  When the URL contains lat-max/lat-min/
     lon-max/lon-min we filter the estate IDs to only those that fall inside
     the bounding box before doing the expensive detail scrapes.
"""

import logging
import time
from typing import Optional
from urllib.parse import urlparse, parse_qs, unquote

import httpx

from backend.scrapers.sreality import scrape_sreality
from backend.scrapers.constants import HEADERS_API as HEADERS, DISP_TO_CODE

logger = logging.getLogger(__name__)

PER_PAGE = 20
REQUEST_DELAY = 0.25   # seconds between detail fetches – be polite

# ---------------------------------------------------------------------------
# Mapping tables
# ---------------------------------------------------------------------------

TRANSACTION_MAP = {"prodej": 1, "pronajem": 2}
TYPE_MAP = {"byty": 1, "domy": 2, "pozemky": 3, "komercni": 4, "ostatni": 5}


# Confirmed Sreality locality_region_id values (verified via API):
#   1=Jihočeský  2=Plzeňský   3=Karlovarský   4=Ústecký    5=Liberecký
#   6=Královéhradecký  7=Pardubický  8=Olomoucký  9=Zlínský  10=Praha
#   11=Středočeský  12=Moravskoslezský  13=Kraj Vysočina  14=Jihomoravský
LOCALITY_TO_REGION: dict[str, int] = {
    # Praha
    "praha": 10,
    # Jihočeský kraj (1)
    "ceske-budejovice": 1, "jindrichuv-hradec": 1, "pisek": 1,
    "prachatice": 1, "strakonice": 1, "tabor": 1, "cesky-krumlov": 1,
    # Plzeňský kraj (2)
    "plzen": 2, "klatovy": 2, "domazlice": 2, "rokycany": 2, "tachov": 2,
    # Karlovarský kraj (3)
    "karlovy-vary": 3, "cheb": 3, "sokolov": 3,
    # Ústecký kraj (4)
    "teplice": 4, "most": 4, "decin": 4, "chomutov": 4,
    "litomerice": 4, "louny": 4, "usti-nad-labem": 4,
    # Liberecký kraj (5)
    "liberec": 5, "jablonec-nad-nisou": 5, "ceska-lipa": 5, "semily": 5,
    # Královéhradecký kraj (6)
    "hradec-kralove": 6, "jicin": 6, "nachod": 6,
    "rychnov-nad-kneznou": 6, "trutnov": 6,
    # Pardubický kraj (7)
    "pardubice": 7, "chrudim": 7, "svitavy": 7, "usti-nad-orlici": 7,
    # Olomoucký kraj (8)
    "olomouc": 8, "prerov": 8, "prostejov": 8, "sumperk": 8, "jesenik": 8,
    # Zlínský kraj (9)
    "zlin": 9, "vsetin": 9, "kromeriz": 9, "uherske-hradiste": 9,
    # Středočeský kraj (11)
    "melnik": 11, "beroun": 11, "kladno": 11, "kolin": 11,
    "kutna-hora": 11, "mlada-boleslav": 11, "nymburk": 11,
    "pribram": 11, "rakovnik": 11, "benesov": 11,
    # Moravskoslezský kraj (12)
    "ostrava": 12, "frydek-mistek": 12, "karvina": 12,
    "novy-jicin": 12, "opava": 12, "bruntal": 12,
    # Kraj Vysočina (13)
    "jihlava": 13, "havlickuv-brod": 13, "pelhrimov": 13,
    "trebic": 13, "zdar-nad-sazavou": 13,
    # Jihomoravský kraj (14)
    "brno": 14, "blansko": 14, "breclav": 14, "hodonin": 14,
    "vyskov": 14, "znojmo": 14,
}


# ---------------------------------------------------------------------------
# URL → API params + bounding box
# ---------------------------------------------------------------------------

def parse_search_url(url: str) -> tuple[dict, dict | None]:
    """
    Convert a Sreality search UI URL to Sreality API query parameters.

    Returns:
        (api_params, bbox)
        where bbox is None or {"lat_min", "lat_max", "lon_min", "lon_max"}
    """
    parsed = urlparse(url)
    path_parts = [p for p in parsed.path.split("/") if p]
    # Expected: ["hledani", "prodej", "byty", "teplice"] (locality optional)

    params: dict = {}
    bbox: dict | None = None

    if len(path_parts) >= 2:
        params["category_main_cb"] = TRANSACTION_MAP.get(path_parts[1], 1)

    if len(path_parts) >= 3:
        params["category_type_cb"] = TYPE_MAP.get(path_parts[2], 1)

    # Map locality slug → locality_region_id for API pre-filtering
    if len(path_parts) >= 4:
        locality_slug = path_parts[3].lower()
        region_id = LOCALITY_TO_REGION.get(locality_slug)
        if region_id:
            params["locality_region_id"] = region_id
            logger.info("Locality '%s' → region_id=%d", locality_slug, region_id)
        else:
            logger.warning("Unknown locality slug '%s', no region filter applied", locality_slug)

    raw_query = unquote(parsed.query)
    qs = parse_qs(raw_query, keep_blank_values=True)

    # Dispositions – Sreality API accepts repeated category_sub_cb params
    velikost_raw = qs.get("velikost", [""])[0]
    if velikost_raw:
        disps = [d.strip() for d in velikost_raw.split(",")]
        sub_cbs = [DISP_TO_CODE[d] for d in disps if d in DISP_TO_CODE]
        if sub_cbs:
            params["category_sub_cb"] = sub_cbs
        logger.info("Dispositions parsed: %s → codes %s", disps, sub_cbs)

    # Price range
    if "cena-od" in qs:
        params["price_from"] = qs["cena-od"][0]
    if "cena-do" in qs:
        params["price_to"] = qs["cena-do"][0]

    # Size range
    if "plocha-od" in qs:
        params["usable_area_from"] = qs["plocha-od"][0]
    if "plocha-do" in qs:
        params["usable_area_to"] = qs["plocha-do"][0]

    # Bounding box – the Sreality API ignores lat/lon query params, so we
    # store them separately for GPS post-filtering in collect_estate_ids.
    try:
        if all(k in qs for k in ("lat-max", "lat-min", "lon-max", "lon-min")):
            bbox = {
                "lat_min": float(qs["lat-min"][0]),
                "lat_max": float(qs["lat-max"][0]),
                "lon_min": float(qs["lon-min"][0]),
                "lon_max": float(qs["lon-max"][0]),
            }
            logger.info("Bounding box: %s", bbox)
    except (ValueError, KeyError):
        pass

    logger.info("Parsed search params: %s, bbox: %s", params, bbox)
    return params, bbox


# ---------------------------------------------------------------------------
# Pagination – collect estate IDs (with optional GPS post-filter)
# ---------------------------------------------------------------------------

def collect_estate_ids(
    api_params: dict,
    bbox: dict | None = None,
) -> tuple[list[int], int]:
    """
    Paginate through ALL Sreality search results and return estate IDs.

    If bbox is provided, only returns estates whose GPS coordinates fall
    within {"lat_min", "lat_max", "lon_min", "lon_max"}.

    Returns:
        (list_of_estate_ids, total_found_count)
    """
    ids: list[int] = []
    total_found = 0
    page = 1

    with httpx.Client(headers=HEADERS, timeout=15) as client:
        while True:
            params = {**api_params, "per_page": PER_PAGE, "page": page}
            resp = client.get("https://www.sreality.cz/api/cs/v2/estates", params=params)

            if resp.status_code != 200:
                logger.warning("Search page %d returned %s", page, resp.status_code)
                break

            data = resp.json()
            total_found = int(data.get("result_size", 0))
            estates = data.get("_embedded", {}).get("estates", [])

            if not estates:
                break

            for estate in estates:
                href = estate.get("_links", {}).get("self", {}).get("href", "")
                if not href:
                    continue
                try:
                    estate_id = int(href.rstrip("/").split("/")[-1])
                except ValueError:
                    continue

                # GPS bounding box post-filter
                if bbox:
                    gps = estate.get("gps") or {}
                    lat = gps.get("lat")
                    lon = gps.get("lon")
                    if lat is None or lon is None:
                        continue  # skip estates without GPS data
                    if not (bbox["lat_min"] <= lat <= bbox["lat_max"] and
                            bbox["lon_min"] <= lon <= bbox["lon_max"]):
                        continue  # outside requested area

                ids.append(estate_id)

            logger.info(
                "Page %d: %d IDs collected so far (total available: %d, bbox_filter=%s)",
                page, len(ids), total_found, bbox is not None,
            )

            if page * PER_PAGE >= total_found:
                break
            page += 1

    return ids, total_found


# ---------------------------------------------------------------------------
# Full scrape of each estate
# ---------------------------------------------------------------------------

def full_scrape_search(
    url: str,
    progress_callback=None,
) -> dict:
    """
    Full pipeline: parse URL → collect IDs (with GPS filtering) → scrape each detail.

    Args:
        url:               Sreality search URL
        progress_callback: optional callable(current, total, estate_id)

    Returns:
        {
            "total_found":   int,   # total in search results (pre-GPS-filter)
            "total_scraped": int,   # successfully scraped
            "properties":    list[dict],
            "errors":        list[str],
        }
    """
    api_params, bbox = parse_search_url(url)
    estate_ids, total_found = collect_estate_ids(api_params, bbox=bbox)

    properties: list[dict] = []
    errors: list[str] = []

    for i, estate_id in enumerate(estate_ids):
        estate_url = f"https://www.sreality.cz/detail/-/-/-/-/{estate_id}"
        if progress_callback:
            progress_callback(i + 1, len(estate_ids), estate_id)
        try:
            prop = scrape_sreality(estate_url)
            properties.append(prop)
        except Exception as exc:
            msg = f"Estate {estate_id}: {exc}"
            logger.warning(msg)
            errors.append(msg)

        # Polite delay between detail requests
        if i < len(estate_ids) - 1:
            time.sleep(REQUEST_DELAY)

    return {
        "total_found": total_found,
        "total_scraped": len(properties),
        "properties": properties,
        "errors": errors,
    }
