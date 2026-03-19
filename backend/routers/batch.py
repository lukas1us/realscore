"""
POST /api/batch-analyze

Accepts a Sreality search URL, scrapes all matching estates,
scores each one, saves to DB and returns sorted results.

Deduplication: estate IDs already present in the DB are skipped before
any detail scrape, avoiding redundant HTTP requests and duplicate rows.
"""

import logging
import re
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Property
from backend.schemas import BatchInput, BatchResult, PropertyListItem
from backend.services.scoring import compute_scores
from backend.utils.regions import extract_kraj

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["batch"])

REQUEST_DELAY = 0.25  # seconds between detail fetches


def _known_estate_ids(db: Session) -> set[int]:
    """Return the set of Sreality estate IDs already stored in the DB."""
    ids: set[int] = set()
    for prop in db.query(Property).filter(Property.url.isnot(None)).all():
        m = re.search(r"/(\d{5,})(?:[/?]|$)", prop.url)
        if m:
            ids.add(int(m.group(1)))
    return ids


@router.post("/batch-analyze", response_model=BatchResult)
def batch_analyze(payload: BatchInput, db: Session = Depends(get_db)):
    """
    Scrape a Sreality search page (with pagination) and score every listing.
    Already-analysed estates (matched by estate ID in URL) are skipped.
    """
    from backend.scrapers.sreality_search import parse_search_url, collect_estate_ids
    from backend.scrapers.sreality import scrape_sreality

    if "sreality" not in payload.url.lower():
        raise HTTPException(
            status_code=422,
            detail="Hromadná analýza momentálně podporuje pouze Sreality vyhledávání.",
        )

    # 1. Collect estate IDs from search (with GPS post-filter if bbox present)
    try:
        api_params, bbox = parse_search_url(payload.url)
        estate_ids, total_found = collect_estate_ids(api_params, bbox=bbox)
    except Exception as exc:
        logger.error("Batch collect failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Chyba při scrapování: {exc}")

    # 2. Deduplicate – filter out IDs already in the DB
    known_ids = _known_estate_ids(db)
    new_ids = [eid for eid in estate_ids if eid not in known_ids]
    skipped_count = len(estate_ids) - len(new_ids)
    logger.info(
        "Batch: %d IDs found, %d skipped (already in DB), %d to scrape",
        len(estate_ids), skipped_count, len(new_ids),
    )

    # 3. Scrape only new estates
    properties: list[dict] = []
    errors: list[str] = []

    for i, estate_id in enumerate(new_ids):
        estate_url = f"https://www.sreality.cz/detail/-/-/-/-/{estate_id}"
        try:
            prop = scrape_sreality(estate_url)
            properties.append(prop)
        except Exception as exc:
            msg = f"Estate {estate_id}: {exc}"
            logger.warning(msg)
            errors.append(msg)
        if i < len(new_ids) - 1:
            time.sleep(REQUEST_DELAY)

    # 4. Score and save
    saved: list[PropertyListItem] = []

    for prop in properties:
        try:
            scores = compute_scores(prop)

            price_per_m2: Optional[float] = None
            if prop.get("price") and prop.get("size_m2") and prop["size_m2"] > 0:
                price_per_m2 = prop["price"] / prop["size_m2"]

            db_obj = Property(
                url=prop.get("url"),
                address=prop.get("address"),
                city=prop.get("city"),
                district=prop.get("district"),
                price=prop.get("price"),
                size_m2=prop.get("size_m2"),
                disposition=prop.get("disposition"),
                construction_type=prop.get("construction_type"),
                energy_class=prop.get("energy_class"),
                year_built=prop.get("year_built"),
                floor=prop.get("floor"),
                has_elevator=prop.get("has_elevator"),
                # city_stigma je auto-computed v compute_scores() dle názvu města
                city_stigma=scores.get("city_stigma"),
                kraj=extract_kraj(prop.get("city"), prop.get("district")),
                score_total=scores["score_total"],
                score_yield=scores["score_yield"],
                score_demographic=scores["score_demographic"],
                score_economic=scores["score_economic"],
                score_quality=scores["score_quality"],
                score_liquidity=scores["score_liquidity"],
                estimated_rent=scores.get("estimated_rent"),
                gross_yield_pct=scores.get("gross_yield_pct"),
                raw_data=prop.get("raw_data"),
            )
            db.add(db_obj)
            db.flush()  # get ID without committing yet

            saved.append(PropertyListItem(
                id=db_obj.id,
                url=db_obj.url,
                address=db_obj.address,
                city=db_obj.city,
                price=db_obj.price,
                size_m2=db_obj.size_m2,
                disposition=db_obj.disposition,
                score_total=scores["score_total"],
                gross_yield_pct=scores.get("gross_yield_pct"),
                energy_class=db_obj.energy_class,
                created_at=db_obj.created_at,
            ))
        except Exception as exc:
            errors.append(f"Scoring failed for {prop.get('url', '?')}: {exc}")
            logger.warning("Scoring/save failed: %s", exc)

    db.commit()

    # Sort by score descending
    saved.sort(key=lambda p: p.score_total or 0, reverse=True)

    return BatchResult(
        total_found=total_found,
        total_matching=len(estate_ids),   # GPS-filtered count (before dedup)
        total_scraped=len(properties),
        total_saved=len(saved),
        total_skipped=skipped_count,
        properties=saved,
        errors=errors,
    )
