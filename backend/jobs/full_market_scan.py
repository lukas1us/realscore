"""
full_market_scan.py — Standalone job: download ALL Sreality apartment listings
(sale, up to a configurable price cap) and save scored results to the database.

Strategy to bypass the ~1 000-result Sreality API cap
──────────────────────────────────────────────────────
The Sreality /api/cs/v2/estates endpoint returns at most ~1 000 results per
query (50 pages × 20 items).  We work around this by subdividing the search
space into buckets small enough to fit within that cap:

  1. For each of the 14 Czech regions, query with price_to=<price_max>.
  2. If a region's result_size ≤ BUCKET_LIMIT → collect all IDs directly.
  3. If result_size > BUCKET_LIMIT → subdivide further by disposition code
     (1+kk, 1+1, 2+kk, … 6+), collecting IDs per sub-bucket.
  4. All IDs are deduplicated (set) so overlapping buckets don't cause dupes.

Deduplication against the DB
─────────────────────────────
Before scraping, the job fetches the estate IDs already stored in the
`properties` table (extracted from the URL).  Only truly new IDs are scraped.

Parallelism
───────────
  ID collection  – region probes, disposition probes, and paginated ID
                   collection all run in a thread pool (ID_WORKERS threads).
  Detail scraping – SCRAPE_WORKERS threads each scrape one estate and compute
                   its scores.  DB writes stay on the main thread to avoid
                   SQLAlchemy session sharing across threads.

Usage
─────
  # From the project root:
  python -m backend.jobs.full_market_scan
  python -m backend.jobs.full_market_scan --price-max 3000000
  python -m backend.jobs.full_market_scan --dry-run        # count only, no DB writes
  python -m backend.jobs.full_market_scan --region 14      # single region (debug)
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

import httpx

from backend.database import SessionLocal
from backend.models import Property
from backend.scrapers.sreality import scrape_sreality, HEADERS
from backend.scrapers.sreality_search import collect_estate_ids
from backend.services.scoring import compute_scores

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PRICE_MAX_DEFAULT = 5_000_000
REQUEST_DELAY = 0.3       # seconds between detail fetches (per worker)
BUCKET_LIMIT = 950        # if region result_size exceeds this, subdivide by disposition

# Sreality ownership codes: 1=osobní, 2=družstevní, 3=státní/obecní
# TODO: remove this filter (and its use in base_params) once all ownership types are desired
OWNERSHIP_PERSONAL = 1

# All 14 Sreality region IDs
ALL_REGIONS = list(range(1, 15))

# Sreality category_sub_cb disposition codes (1+kk … 6+)
ALL_DISPOSITIONS = [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]

# Commit to DB every N saves to avoid a giant single transaction
COMMIT_BATCH = 50

# Thread-pool sizes
ID_WORKERS = 8       # for cheap _result_size probes and paginated ID collection
SCRAPE_WORKERS = 5   # for concurrent detail scrape + scoring


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _known_estate_ids(db) -> set[int]:
    """Return set of estate IDs already stored in the database."""
    rows = db.query(Property.url).filter(Property.url.isnot(None)).all()
    known: set[int] = set()
    for (url,) in rows:
        m = re.search(r"/(\d{5,})(?:[/?]|$)", url)
        if m:
            known.add(int(m.group(1)))
    return known


def _result_size(params: dict) -> int:
    """Fetch result_size for a given set of API params (1 cheap request)."""
    try:
        with httpx.Client(headers=HEADERS, timeout=15) as client:
            resp = client.get(
                "https://www.sreality.cz/api/cs/v2/estates",
                params={**params, "per_page": 1, "page": 1},
            )
            if resp.status_code == 200:
                return int(resp.json().get("result_size", 0))
    except Exception as exc:
        logger.warning("result_size probe failed: %s", exc)
    return 0


def _scrape_and_score(
    estate_id: int,
    price_max: int,
) -> tuple[int, dict | None, str | None]:
    """
    Worker function: scrape one estate detail and compute all scores.

    Returns (estate_id, result_dict | None, error_msg | None).
    result_dict is None when the estate should be skipped (price over cap or error).
    """
    url = f"https://www.sreality.cz/detail/-/-/-/-/{estate_id}"
    try:
        prop_data = scrape_sreality(url)

        # Sreality API price filter is not strict – detail price can exceed
        # the search cap. Drop listings whose scraped price is over the limit.
        detail_price = prop_data.get("price")
        if detail_price and detail_price > price_max:
            logger.debug(
                "Estate %d skipped: price %.0f > price_max %d",
                estate_id, detail_price, price_max,
            )
            return estate_id, None, None

        scores = compute_scores(prop_data)
        return estate_id, {**prop_data, "_scores": scores}, None

    except Exception as exc:
        return estate_id, None, f"Estate {estate_id}: {exc}"

    finally:
        time.sleep(REQUEST_DELAY)  # polite delay per worker thread


# ---------------------------------------------------------------------------
# ID collection
# ---------------------------------------------------------------------------

def collect_all_ids(
    price_max: int,
    region_filter: Optional[int] = None,
) -> list[int]:
    """
    Collect ALL estate IDs for apartments (sale) up to price_max CZK.

    Uses a thread pool to parallelize region probes, disposition probes,
    and paginated ID collection.  Returns a deduplicated list.
    """
    base_params = {
        "category_main_cb": 1,          # prodej (sale)
        "category_type_cb": 1,          # byty (apartments)
        "price_to": price_max,
        "ownership": OWNERSHIP_PERSONAL, # TODO: remove to include all ownership types
    }

    regions = [region_filter] if region_filter else ALL_REGIONS

    # Phase 1: probe all regions in parallel ─────────────────────────────────
    region_params_map = {
        rid: {**base_params, "locality_region_id": rid} for rid in regions
    }
    region_counts: dict[int, int] = {}
    with ThreadPoolExecutor(max_workers=ID_WORKERS) as executor:
        futures = {
            executor.submit(_result_size, params): rid
            for rid, params in region_params_map.items()
        }
        for future in as_completed(futures):
            rid = futures[future]
            region_counts[rid] = future.result()
            logger.info("Region %2d: %d listings", rid, region_counts[rid])

    # Phase 2: build final collection buckets ─────────────────────────────────
    # For large regions, probe all dispositions in parallel first.
    collection_buckets: list[dict] = []

    large_regions = [rid for rid, cnt in region_counts.items() if cnt > BUCKET_LIMIT]
    small_regions = [rid for rid, cnt in region_counts.items() if 0 < cnt <= BUCKET_LIMIT]

    # Small regions go directly as buckets
    for rid in small_regions:
        collection_buckets.append(region_params_map[rid])

    # Large regions: probe dispositions in parallel
    if large_regions:
        disp_probe_args: list[tuple[int, int, dict]] = []
        for rid in large_regions:
            for dc in ALL_DISPOSITIONS:
                params = {**region_params_map[rid], "category_sub_cb": dc}
                disp_probe_args.append((rid, dc, params))

        with ThreadPoolExecutor(max_workers=ID_WORKERS) as executor:
            futures = {
                executor.submit(_result_size, params): (rid, dc)
                for rid, dc, params in disp_probe_args
            }
            for future in as_completed(futures):
                rid, dc = futures[future]
                disp_count = future.result()
                if disp_count == 0:
                    continue
                if disp_count > BUCKET_LIMIT:
                    logger.warning(
                        "Region %d / disp %d still has %d results "
                        "(above cap – some listings may be missed)",
                        rid, dc, disp_count,
                    )
                collection_buckets.append({**region_params_map[rid], "category_sub_cb": dc})

    logger.info("Collecting IDs from %d buckets …", len(collection_buckets))

    # Phase 3: collect IDs from all buckets in parallel ───────────────────────
    # Network errors in individual buckets are caught and logged; the job
    # continues with the remaining buckets instead of crashing entirely.
    all_ids: set[int] = set()
    with ThreadPoolExecutor(max_workers=ID_WORKERS) as executor:
        futures = {
            executor.submit(collect_estate_ids, params, None): params
            for params in collection_buckets
        }
        for future in as_completed(futures):
            try:
                ids, _ = future.result()
                new_count = len(set(ids) - all_ids)
                all_ids.update(ids)
                logger.debug("Bucket done: +%d IDs (total so far: %d)", new_count, len(all_ids))
            except Exception as exc:
                logger.warning("Bucket failed, skipping: %s", exc)

    return list(all_ids)


# ---------------------------------------------------------------------------
# Main scan
# ---------------------------------------------------------------------------

def run_scan(
    price_max: int = PRICE_MAX_DEFAULT,
    dry_run: bool = False,
    region_filter: Optional[int] = None,
) -> dict:
    """
    Full pipeline:
      1. Collect all estate IDs from Sreality (with subdivision, parallel).
      2. Deduplicate against existing DB records.
      3. Scrape + score each new estate in a thread pool.
      4. Write results to the DB on the main thread (thread-safe).

    Returns a summary dict.
    """
    logger.info(
        "=== Full market scan START  price_max=%d  dry_run=%s  region=%s  workers=%d ===",
        price_max, dry_run, region_filter or "all", SCRAPE_WORKERS,
    )

    db = SessionLocal()
    try:
        known_ids = _known_estate_ids(db)
        logger.info("Already in DB: %d properties", len(known_ids))

        all_ids = collect_all_ids(price_max, region_filter=region_filter)
        logger.info("Total unique IDs from Sreality: %d", len(all_ids))

        new_ids = [eid for eid in all_ids if eid not in known_ids]
        skipped = len(all_ids) - len(new_ids)
        logger.info("New (not yet in DB): %d  |  Skipped (already saved): %d", len(new_ids), skipped)

        if dry_run:
            logger.info("Dry run – skipping scrape & DB writes.")
            return {
                "total_found": len(all_ids),
                "new": len(new_ids),
                "skipped": skipped,
                "scraped": 0,
                "saved": 0,
                "errors": [],
            }

        errors: list[str] = []
        saved = 0
        completed = 0

        with ThreadPoolExecutor(max_workers=SCRAPE_WORKERS) as executor:
            futures = {
                executor.submit(_scrape_and_score, eid, price_max): eid
                for eid in new_ids
            }

            for future in as_completed(futures):
                estate_id = futures[future]
                estate_id, result, error = future.result()
                completed += 1

                if error:
                    logger.warning(error)
                    errors.append(error)
                    continue

                if result is None:
                    # Price over cap – already logged at DEBUG level
                    skipped += 1
                    continue

                scores = result.pop("_scores")
                prop_data = result

                db_prop = Property(
                    url=prop_data.get("url") or f"https://www.sreality.cz/detail/-/-/-/-/{estate_id}",
                    address=prop_data.get("address"),
                    city=prop_data.get("city"),
                    district=prop_data.get("district"),
                    price=prop_data.get("price"),
                    size_m2=prop_data.get("size_m2"),
                    disposition=prop_data.get("disposition"),
                    construction_type=prop_data.get("construction_type"),
                    energy_class=prop_data.get("energy_class"),
                    year_built=prop_data.get("year_built"),
                    floor=prop_data.get("floor"),
                    has_elevator=prop_data.get("has_elevator"),
                    score_total=scores.get("score_total"),
                    score_yield=scores.get("score_yield"),
                    score_demographic=scores.get("score_demographic"),
                    score_economic=scores.get("score_economic"),
                    score_quality=scores.get("score_quality"),
                    score_liquidity=scores.get("score_liquidity"),
                    estimated_rent=scores.get("estimated_rent"),
                    gross_yield_pct=scores.get("gross_yield_pct"),
                    raw_data=prop_data.get("raw_data"),
                )
                db.add(db_prop)
                db.flush()
                saved += 1

                if saved % COMMIT_BATCH == 0:
                    db.commit()
                    logger.info(
                        "Progress: %d / %d done  |  %d saved  (%.1f %%)",
                        completed, len(new_ids), saved,
                        completed / len(new_ids) * 100,
                    )

        db.commit()
        logger.info("=== Scan complete: %d saved, %d errors ===", saved, len(errors))

        return {
            "total_found": len(all_ids),
            "new": len(new_ids),
            "skipped": skipped,
            "scraped": saved + len(errors),
            "saved": saved,
            "errors": errors,
        }

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
        description="Full Sreality market scan – apartments for sale up to a price cap."
    )
    parser.add_argument(
        "--price-max",
        type=int,
        default=PRICE_MAX_DEFAULT,
        metavar="CZK",
        help=f"Maximum purchase price in CZK (default: {PRICE_MAX_DEFAULT:,})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Count IDs only – do not scrape details or write to the database",
    )
    parser.add_argument(
        "--region",
        type=int,
        default=None,
        metavar="1-14",
        help="Restrict scan to a single Sreality region ID (useful for testing)",
    )
    args = parser.parse_args()

    result = run_scan(
        price_max=args.price_max,
        dry_run=args.dry_run,
        region_filter=args.region,
    )

    print("\n=== Summary ===")
    print(f"  Total found on Sreality : {result['total_found']}")
    print(f"  Already in DB (skipped)  : {result['skipped']}")
    print(f"  New properties scraped   : {result['scraped']}")
    print(f"  Successfully saved       : {result['saved']}")
    print(f"  Errors                   : {len(result['errors'])}")
    if result["errors"]:
        print("\nFirst 10 errors:")
        for err in result["errors"][:10]:
            print(f"  {err}")

    sys.exit(0 if not result["errors"] else 1)
