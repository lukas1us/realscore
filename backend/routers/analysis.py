"""
/api/analyze  – accepts PropertyInput, runs scraping + scoring, saves to DB.
"""

import logging
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Property
from backend.schemas import PropertyInput, PropertyResult, ScoreBreakdown
from backend.services.scoring import compute_scores, _build_summary, _build_red_flags, STIGMATIZED_CITIES
from backend.utils.regions import extract_kraj

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["analysis"])


def _find_existing(db: Session, url: str) -> Optional[Property]:
    """Return an existing Property row matching this URL, or None."""
    # Try exact URL match first
    existing = db.query(Property).filter(Property.url == url).first()
    if existing:
        return existing
    # For Sreality: match by estate_id suffix (handles URL format variations)
    if "sreality" in url.lower():
        m = re.search(r"/(\d{5,})(?:[/?]|$)", url)
        if m:
            eid = m.group(1)
            existing = db.query(Property).filter(
                Property.url.like(f"%/{eid}")
            ).first()
    return existing


def _property_result_from_db(r: Property) -> PropertyResult:
    """Reconstruct a PropertyResult from a stored Property row."""
    scores = {
        "score_yield": r.score_yield or 0,
        "score_demographic": r.score_demographic or 0,
        "score_economic": r.score_economic or 0,
        "score_quality": r.score_quality or 0,
        "score_liquidity": r.score_liquidity or 0,
        "score_total": r.score_total or 0,
        "gross_yield_pct": r.gross_yield_pct,
    }
    prop = {
        "city": r.city, "district": r.district, "price": r.price,
        "size_m2": r.size_m2, "construction_type": r.construction_type,
        "energy_class": r.energy_class, "year_built": r.year_built,
        "ownership": r.ownership, "svl_risk": r.svl_risk,
        "locality_tier": r.locality_tier, "city_stigma": r.city_stigma,
        "building_revitalized": r.building_revitalized,
        "floor": r.floor,
    }
    price_per_m2 = (r.price / r.size_m2) if (r.price and r.size_m2 and r.size_m2 > 0) else None
    return PropertyResult(
        id=r.id,
        url=r.url,
        address=r.address,
        city=r.city,
        district=r.district,
        price=r.price,
        size_m2=r.size_m2,
        disposition=r.disposition,
        construction_type=r.construction_type,
        energy_class=r.energy_class,
        year_built=r.year_built,
        floor=r.floor,
        has_elevator=r.has_elevator,
        scores=ScoreBreakdown(
            score_yield=scores["score_yield"],
            score_demographic=scores["score_demographic"],
            score_economic=scores["score_economic"],
            score_quality=scores["score_quality"],
            score_liquidity=scores["score_liquidity"],
            score_total=scores["score_total"],
        ),
        estimated_rent=r.estimated_rent,
        gross_yield_pct=r.gross_yield_pct,
        price_per_m2=price_per_m2,
        ownership=r.ownership,
        building_revitalized=r.building_revitalized,
        service_charge=r.service_charge,
        svl_risk=r.svl_risk,
        locality_tier=r.locality_tier,
        city_stigma=r.city_stigma,
        summary=_build_summary(scores, prop),
        red_flags=_build_red_flags(scores, prop),
        created_at=r.created_at,
    )


def _detect_portal(url: str) -> str:
    low = url.lower()
    if "sreality" in low:
        return "sreality"
    if "bezrealitky" in low:
        return "bezrealitky"
    if "reality.idnes" in low:
        return "idnes"
    return "unknown"


def _scrape(url: str) -> dict:
    portal = _detect_portal(url)
    if portal == "sreality":
        from backend.scrapers.sreality import scrape_sreality
        return scrape_sreality(url)
    elif portal == "bezrealitky":
        from backend.scrapers.bezrealitky import scrape_bezrealitky
        return scrape_bezrealitky(url)
    elif portal == "idnes":
        from backend.scrapers.idnes import scrape_idnes
        return scrape_idnes(url)
    raise ValueError(f"Nepodporovaný portál pro URL: {url}")


@router.post("/analyze", response_model=PropertyResult)
def analyze(payload: PropertyInput, db: Session = Depends(get_db)):
    """
    Main endpoint: scrape URL (if provided) or use manual fields, score and save.
    """
    prop: dict = {}

    # 0. Duplicate check – avoid re-scraping already analysed listings
    if payload.url:
        existing = _find_existing(db, payload.url)
        if existing:
            logger.info("Duplicate detected (id=%d), returning existing record", existing.id)
            return _property_result_from_db(existing)

    # 1. Scraping phase
    if payload.url:
        try:
            prop = _scrape(payload.url)
        except Exception as exc:
            logger.warning("Scraping failed (%s), using manual fields: %s", payload.url, exc)
            prop = {}

    # 2. Merge manual overrides (manual fields win over scraped)
    manual = payload.model_dump(exclude={"url"}, exclude_none=True)
    prop.update(manual)
    prop.setdefault("url", payload.url)

    # 3. Validate we have enough data
    if not prop.get("price") and not prop.get("size_m2"):
        raise HTTPException(
            status_code=422,
            detail="Nepodařilo se získat data o nemovitosti. Vyplňte parametry ručně.",
        )

    # 4. Scoring
    scores = compute_scores(prop)

    # 5. Persist to DB
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
        # Nová pole
        ownership=prop.get("ownership"),
        building_revitalized=prop.get("building_revitalized"),
        service_charge=prop.get("service_charge"),
        svl_risk=prop.get("svl_risk"),
        locality_tier=prop.get("locality_tier"),
        city_stigma=scores.get("city_stigma"),  # auto-computed v compute_scores()
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
    db.commit()
    db.refresh(db_obj)

    return PropertyResult(
        id=db_obj.id,
        url=db_obj.url,
        address=db_obj.address,
        city=db_obj.city,
        district=db_obj.district,
        price=db_obj.price,
        size_m2=db_obj.size_m2,
        disposition=db_obj.disposition,
        construction_type=db_obj.construction_type,
        energy_class=db_obj.energy_class,
        year_built=db_obj.year_built,
        floor=db_obj.floor,
        has_elevator=db_obj.has_elevator,
        ownership=db_obj.ownership,
        building_revitalized=db_obj.building_revitalized,
        service_charge=db_obj.service_charge,
        svl_risk=db_obj.svl_risk,
        locality_tier=db_obj.locality_tier,
        city_stigma=db_obj.city_stigma,
        scores=ScoreBreakdown(
            score_yield=scores["score_yield"],
            score_demographic=scores["score_demographic"],
            score_economic=scores["score_economic"],
            score_quality=scores["score_quality"],
            score_liquidity=scores["score_liquidity"],
            score_total=scores["score_total"],
        ),
        estimated_rent=scores.get("estimated_rent"),
        gross_yield_pct=scores.get("gross_yield_pct"),
        price_per_m2=price_per_m2,
        summary=scores["summary"],
        red_flags=scores["red_flags"],
        created_at=db_obj.created_at,
    )
