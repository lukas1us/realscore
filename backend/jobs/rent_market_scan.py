"""
rent_market_scan.py — Populate rent_benchmarks from live Sreality rental listings.

For each distinct (city, disposition) pair in the properties table the job:
  1. Queries the Sreality rental search API (category_main_cb=2) filtered by
     disposition.  City is mapped to a Sreality region ID when possible
     (via LOCALITY_TO_REGION) so results are geographically relevant; if no
     region mapping is found the search covers all of Czech Republic.
  2. Collects asking rents from search results.
  3. Computes median_rent and listing_count.
  4. Upserts the result into rent_benchmarks.

Duplicates are avoided at the query level — each (city, disposition) pair is
scraped exactly once regardless of how many times it appears in properties.

Usage
─────
  python -m backend.jobs.rent_market_scan
  python -m backend.jobs.rent_market_scan --dry-run
  python -m backend.jobs.rent_market_scan --request-delay 1.0 --max-retries 3
"""

from __future__ import annotations

import argparse
import logging
import re
import statistics
import sys
import time
from typing import Optional

import httpx

from backend.database import SessionLocal
from backend.models import Property, RentBenchmark
from backend.scrapers.constants import HEADERS_API as HEADERS, DISP_TO_CODE
from backend.scrapers.sreality_search import LOCALITY_TO_REGION

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REQUEST_DELAY_DEFAULT = 0.5
MAX_RETRIES_DEFAULT = 3

SREALITY_SEARCH_URL = "https://www.sreality.cz/api/cs/v2/estates"
PER_PAGE = 20  # one page is enough for a median estimate


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _city_to_region_id(city: str) -> Optional[int]:
    """Try to map a city name to a Sreality locality_region_id."""
    if not city:
        return None
    slug = city.lower().strip()
    # Direct match (e.g. "teplice" → 4)
    if slug in LOCALITY_TO_REGION:
        return LOCALITY_TO_REGION[slug]
    # Strip diacritics naively for common cases
    slug_ascii = (
        slug.replace("á", "a").replace("č", "c").replace("ď", "d")
            .replace("é", "e").replace("ě", "e").replace("í", "i")
            .replace("ň", "n").replace("ó", "o").replace("ř", "r")
            .replace("š", "s").replace("ť", "t").replace("ú", "u")
            .replace("ů", "u").replace("ý", "y").replace("ž", "z")
    )
    return LOCALITY_TO_REGION.get(slug_ascii)


def _fetch_rents(
    city: str,
    disposition: str,
    request_delay: float,
    max_retries: int,
) -> tuple[list[float], int]:
    """
    Hit Sreality search API for rentals matching city + disposition.

    Returns (list_of_rents, result_size).
    result_size is the total count reported by the API (may exceed len(rents)).
    """
    sub_cb = DISP_TO_CODE.get(disposition.lower())
    if sub_cb is None:
        logger.debug("Unknown disposition code for '%s', skipping", disposition)
        return [], 0

    region_id = _city_to_region_id(city)

    params: dict = {
        "category_main_cb": 2,  # pronájem
        "category_type_cb": 1,  # byt
        "per_page": PER_PAGE,
        "page": 1,
        "category_sub_cb": sub_cb,
    }
    if region_id:
        params["locality_region_id"] = region_id

    last_exc: Optional[Exception] = None
    for attempt in range(max_retries):
        try:
            with httpx.Client(headers=HEADERS, timeout=15) as client:
                resp = client.get(SREALITY_SEARCH_URL, params=params)
            if request_delay:
                time.sleep(request_delay)

            if resp.status_code == 429:
                wait = 2 ** attempt
                logger.warning("Rate limited (429) for %s/%s, retrying in %ds", city, disposition, wait)
                time.sleep(wait)
                continue
            if resp.status_code in (403, 404):
                logger.debug("HTTP %d for %s/%s, skipping", resp.status_code, city, disposition)
                return [], 0
            if resp.status_code != 200:
                logger.warning("HTTP %d for %s/%s", resp.status_code, city, disposition)
                return [], 0

            data = resp.json()
            result_size: int = int(data.get("result_size", 0))
            estates = data.get("_embedded", {}).get("estates", [])

            rents: list[float] = []
            for estate in estates:
                price = estate.get("price_czk")
                if price and isinstance(price, (int, float)) and price > 0:
                    rents.append(float(price))

            logger.debug(
                "%s / %s: result_size=%d collected=%d rents",
                city, disposition, result_size, len(rents),
            )
            return rents, result_size

        except Exception as exc:
            last_exc = exc
            if attempt < max_retries - 1:
                wait = 2 ** attempt
                logger.warning("Fetch failed for %s/%s: %s — retry in %ds", city, disposition, exc, wait)
                time.sleep(wait)

    logger.warning("All retries exhausted for %s/%s: %s", city, disposition, last_exc)
    return [], 0


# ---------------------------------------------------------------------------
# Main job
# ---------------------------------------------------------------------------

def run_rent_scan(
    dry_run: bool = False,
    request_delay: float = REQUEST_DELAY_DEFAULT,
    max_retries: int = MAX_RETRIES_DEFAULT,
) -> dict:
    """
    Populate rent_benchmarks for all (city, disposition) pairs in properties.

    Returns a summary dict.
    """
    logger.info(
        "=== Rent market scan START  dry_run=%s  request_delay=%.2fs  max_retries=%d ===",
        dry_run, request_delay, max_retries,
    )

    db = SessionLocal()
    try:
        # Deduplicated (city, disposition) pairs from properties table
        rows = (
            db.query(Property.city, Property.disposition)
            .filter(Property.city.isnot(None), Property.disposition.isnot(None))
            .distinct()
            .all()
        )
        pairs = [(r.city, r.disposition) for r in rows]
        logger.info("Unique (city, disposition) pairs to scan: %d", len(pairs))

        if dry_run:
            logger.info("Dry run — no API calls or DB writes.")
            return {"pairs": len(pairs), "upserted": 0, "skipped": 0, "errors": 0}

        upserted = 0
        skipped = 0
        errors = 0

        for city, disposition in pairs:
            rents, result_size = _fetch_rents(city, disposition, request_delay, max_retries)

            if not rents:
                logger.info("No rents found for %s / %s (result_size=%d)", city, disposition, result_size)
                skipped += 1
                continue

            median_rent = int(statistics.median(rents))
            listing_count = result_size  # API-reported total, not just page count

            logger.info(
                "%s / %s → median_rent=%d  listing_count=%d  (sample=%d)",
                city, disposition, median_rent, listing_count, len(rents),
            )

            existing = (
                db.query(RentBenchmark)
                .filter(RentBenchmark.city == city, RentBenchmark.disposition == disposition)
                .first()
            )
            if existing:
                existing.median_rent = median_rent
                existing.listing_count = listing_count
            else:
                db.add(RentBenchmark(
                    city=city,
                    disposition=disposition,
                    median_rent=median_rent,
                    listing_count=listing_count,
                ))

            db.commit()
            upserted += 1

        logger.info(
            "=== Rent scan complete: %d upserted, %d skipped, %d errors ===",
            upserted, skipped, errors,
        )
        return {"pairs": len(pairs), "upserted": upserted, "skipped": skipped, "errors": errors}

    except Exception as exc:
        db.rollback()
        logger.error("Rent scan failed: %s", exc)
        raise
    finally:
        db.close()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-7s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    parser = argparse.ArgumentParser(
        description="Populate rent_benchmarks from live Sreality rental listings."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List pairs without making API calls or DB writes",
    )
    parser.add_argument(
        "--request-delay",
        type=float,
        default=REQUEST_DELAY_DEFAULT,
        metavar="SECONDS",
        help=f"Seconds to sleep after each API request (default: {REQUEST_DELAY_DEFAULT})",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=MAX_RETRIES_DEFAULT,
        metavar="N",
        help=f"Retry attempts on rate-limit/connection errors (default: {MAX_RETRIES_DEFAULT})",
    )
    args = parser.parse_args()

    result = run_rent_scan(
        dry_run=args.dry_run,
        request_delay=args.request_delay,
        max_retries=args.max_retries,
    )

    logger.info("=== Summary ===")
    logger.info("  Pairs scanned : %d", result["pairs"])
    logger.info("  Upserted      : %d", result["upserted"])
    logger.info("  Skipped       : %d", result["skipped"])
    logger.info("  Errors        : %d", result["errors"])
    sys.exit(0 if result["errors"] == 0 else 1)
