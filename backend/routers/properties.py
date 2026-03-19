"""
/api/properties – history listing with sorting and filtering.
"""

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, asc, func, or_
from sqlalchemy.orm import Session, load_only
from sqlalchemy.orm import Query as OrmQuery

from backend.database import get_db
from backend.models import Property
from backend.schemas import PropertyDetail, PropertyListItem
from backend.services.benchmarks import get_benchmark
from backend.services.scoring import _build_red_flags, _build_summary, compute_financial
from backend.utils.regions import CZECH_REGIONS, CITY_TO_REGION, city_to_kraj

router = APIRouter(prefix="/api", tags=["properties"])

SortField = Literal["created_at", "score_total", "gross_yield_pct", "price"]


def _apply_filters(
    q: OrmQuery,
    regions: list[str],
    price_min: Optional[float],
    price_max: Optional[float],
    cities: list[str],
    energy_classes: list[str],
    min_yield: Optional[float],
    ownerships: list[str],
) -> OrmQuery:
    if regions:
        q = q.filter(Property.kraj.in_(regions))

    if price_min is not None:
        q = q.filter(Property.price >= price_min)
    if price_max is not None:
        q = q.filter(Property.price <= price_max)

    # Filtr dle města — kontroluje city i district (záloha pro stará data kde ulice
    # byla uložena do city a obec do district)
    if cities:
        q = q.filter(or_(Property.city.in_(cities), Property.district.in_(cities)))

    # Filtr dle energetické třídy (PENB)
    if energy_classes:
        q = q.filter(Property.energy_class.in_([e.upper() for e in energy_classes]))

    # Minimální hrubý výnos
    if min_yield is not None:
        q = q.filter(Property.gross_yield_pct >= min_yield)

    # Filtr dle vlastnictví
    if ownerships:
        q = q.filter(Property.ownership.in_(ownerships))

    return q


@router.get("/properties/filters")
def get_filters(
    regions: list[str] = Query(default=[]),
    db: Session = Depends(get_db),
):
    # Dostupné kraje — přímo z DB, seřazené dle CZECH_REGIONS
    available_in_db = {
        r[0] for r in
        db.query(Property.kraj)
        .filter(Property.kraj.isnot(None))
        .distinct()
        .all()
    }
    available = [r for r in CZECH_REGIONS if r in available_in_db]

    # Dostupné PENB třídy v DB
    available_energy = sorted({
        r[0] for r in
        db.query(Property.energy_class)
        .filter(Property.energy_class.isnot(None))
        .distinct()
        .all()
    })

    # Města v rámci vybraných krajů (nebo všechna pokud kraj nevybrán).
    # Prohledáváme obě pole (city i district) — stará data mají obec v district,
    # nová data (po opravě scraperu/backfillu) ji mají v city.
    # CITY_TO_REGION safeguard zajistí, že se nezobrazí ulice ani "Ústecký kraj".
    city_q = db.query(Property.city).filter(Property.city.isnot(None))
    dist_q = db.query(Property.district).filter(Property.district.isnot(None))
    if regions:
        city_q = city_q.filter(Property.kraj.in_(regions))
        dist_q = dist_q.filter(Property.kraj.in_(regions))
    raw_cities = (
        {r[0] for r in city_q.distinct().all()} |
        {r[0] for r in dist_q.distinct().all()}
    )
    known_municipalities = set(CITY_TO_REGION.keys()) | {"Praha"}
    available_cities = sorted(
        c for c in raw_cities
        if c in known_municipalities or c.startswith("Praha")
    )

    price_stats = (
        db.query(func.min(Property.price), func.max(Property.price))
        .filter(Property.price.isnot(None))
        .one()
    )

    yield_stats = (
        db.query(func.max(Property.gross_yield_pct))
        .filter(Property.gross_yield_pct.isnot(None))
        .scalar()
    )

    return {
        "regions": available,
        "cities": available_cities,
        "price_min": int(price_stats[0] or 0),
        "price_max": int(price_stats[1] or 10_000_000),
        "energy_classes": available_energy,
        "yield_max": round(yield_stats or 15.0, 1),
    }


@router.get("/properties/count")
def count_properties(
    regions: list[str] = Query(default=[]),
    price_min: Optional[float] = Query(None),
    price_max: Optional[float] = Query(None),
    cities: list[str] = Query(default=[]),
    energy_classes: list[str] = Query(default=[]),
    min_yield: Optional[float] = Query(None),
    ownerships: list[str] = Query(default=[]),
    db: Session = Depends(get_db),
):
    q = db.query(func.count(Property.id))
    q = _apply_filters(q, regions, price_min, price_max, cities, energy_classes, min_yield, ownerships)
    return {"total": q.scalar()}


@router.get("/properties", response_model=list[PropertyListItem])
def list_properties(
    sort_by: SortField = Query("created_at"),
    order: Literal["desc", "asc"] = Query("desc"),
    limit: int = Query(50, le=500),
    offset: int = Query(0, ge=0),
    regions: list[str] = Query(default=[]),
    price_min: Optional[float] = Query(None),
    price_max: Optional[float] = Query(None),
    cities: list[str] = Query(default=[]),
    energy_classes: list[str] = Query(default=[]),
    min_yield: Optional[float] = Query(None),
    ownerships: list[str] = Query(default=[]),
    db: Session = Depends(get_db),
):
    col = getattr(Property, sort_by, Property.created_at)
    order_fn = desc if order == "desc" else asc
    q = (
        db.query(Property)
        .options(load_only(
            Property.id, Property.url, Property.address, Property.city,
            Property.price, Property.size_m2, Property.disposition,
            Property.score_total, Property.gross_yield_pct, Property.created_at,
            Property.locality_tier, Property.energy_class, Property.kraj,
        ))
    )
    q = _apply_filters(q, regions, price_min, price_max, cities, energy_classes, min_yield, ownerships)
    rows = q.order_by(order_fn(col)).offset(offset).limit(limit).all()
    return [
        PropertyListItem(
            id=r.id,
            url=r.url,
            address=r.address,
            city=r.city,
            price=r.price,
            size_m2=r.size_m2,
            disposition=r.disposition,
            score_total=r.score_total,
            gross_yield_pct=r.gross_yield_pct,
            locality_tier=r.locality_tier,
            energy_class=r.energy_class,
            created_at=r.created_at,
        )
        for r in rows
    ]


@router.get("/properties/{property_id}", response_model=PropertyDetail)
def get_property(property_id: int, db: Session = Depends(get_db)):
    r = db.query(Property).filter(Property.id == property_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Nemovitost nenalezena")

    prop = {
        "city": r.city, "district": r.district, "price": r.price,
        "size_m2": r.size_m2, "construction_type": r.construction_type,
        "energy_class": r.energy_class, "year_built": r.year_built,
        "ownership": r.ownership, "svl_risk": r.svl_risk,
        "locality_tier": r.locality_tier, "city_stigma": r.city_stigma,
        "building_revitalized": r.building_revitalized,
        "floor": r.floor,
    }
    scores = {
        "score_yield": r.score_yield or 0,
        "score_demographic": r.score_demographic or 0,
        "score_economic": r.score_economic or 0,
        "score_quality": r.score_quality or 0,
        "score_liquidity": r.score_liquidity or 0,
        "score_total": r.score_total or 0,
        "gross_yield_pct": r.gross_yield_pct,
    }
    price_per_m2 = (r.price / r.size_m2) if (r.price and r.size_m2 and r.size_m2 > 0) else None

    # Finanční kalkulace
    fin = compute_financial(
        price=r.price,
        estimated_rent=r.estimated_rent,
        service_charge=r.service_charge,
        locality_tier=r.locality_tier,
        svl_risk=r.svl_risk,
        city_stigma=r.city_stigma,
        gross_yield_pct=r.gross_yield_pct,
    )

    # Cenový benchmark
    bm = get_benchmark(db, district=r.district, disposition=r.disposition)
    market_avg_price_m2: float | None = None
    price_vs_market_pct: float | None = None
    benchmark_label: str | None = None
    if bm and price_per_m2:
        market_avg_price_m2 = bm["avg_price_m2"]
        price_vs_market_pct = round((price_per_m2 / market_avg_price_m2 - 1) * 100, 1)
        disp_label = bm["disposition"] or "vše"
        benchmark_label = f"{bm['city']} / {disp_label} (n={bm['sample_size']})"

    return PropertyDetail(
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
        ownership=r.ownership,
        building_revitalized=r.building_revitalized,
        service_charge=r.service_charge,
        svl_risk=r.svl_risk,
        locality_tier=r.locality_tier,
        city_stigma=r.city_stigma,
        kraj=r.kraj,
        score_total=r.score_total,
        score_yield=r.score_yield,
        score_demographic=r.score_demographic,
        score_economic=r.score_economic,
        score_quality=r.score_quality,
        score_liquidity=r.score_liquidity,
        estimated_rent=r.estimated_rent,
        gross_yield_pct=r.gross_yield_pct,
        price_per_m2=price_per_m2,
        collateral_value=fin["collateral_value"],
        max_mortgage=fin["max_mortgage"],
        net_yield_pct=fin["net_yield_pct"],
        monthly_cashflow=fin["monthly_cashflow"],
        market_avg_price_m2=market_avg_price_m2,
        price_vs_market_pct=price_vs_market_pct,
        benchmark_label=benchmark_label,
        summary=_build_summary(scores, prop),
        red_flags=_build_red_flags(scores, prop),
        created_at=r.created_at,
    )


@router.delete("/properties", status_code=204)
def delete_all_properties(db: Session = Depends(get_db)):
    db.query(Property).delete()
    db.commit()


@router.delete("/properties/{property_id}", status_code=204)
def delete_property(property_id: int, db: Session = Depends(get_db)):
    obj = db.query(Property).filter(Property.id == property_id).first()
    if obj:
        db.delete(obj)
        db.commit()
