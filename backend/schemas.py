from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel, ConfigDict


class PropertyInput(BaseModel):
    url: Optional[str] = None
    # Základní parametry
    address: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None
    price: Optional[float] = None
    size_m2: Optional[float] = None
    disposition: Optional[str] = None          # "1+1", "2+kk", etc.
    construction_type: Optional[str] = None    # "panel", "cihla", "smiseny"
    energy_class: Optional[str] = None         # "A" – "G"
    year_built: Optional[int] = None
    floor: Optional[int] = None
    # --- Nová pole pro rozšířený scoring ---
    ownership: Optional[str] = None            # "OV" | "DV" | "DV_no_transfer"
    building_revitalized: Optional[bool] = None
    service_charge: Optional[float] = None     # fond oprav Kč/měsíc
    svl_risk: Optional[str] = None             # "none" | "proximity" | "direct"
    locality_tier: Optional[int] = None        # 1 | 2 | 3
    city_stigma: Optional[bool] = None         # auto-computed if not provided


class ScoreBreakdown(BaseModel):
    # Sémantika sloupců (scoring model v2):
    score_yield: float          # výnosnost (10 %)
    score_demographic: float    # lokalita / SVL čistota (40 %)
    score_economic: float       # PENB / energetická třída (20 %)
    score_quality: float        # fyzické parametry (15 %)
    score_liquidity: float      # vlastnictví OV/DV (15 %)
    score_total: float


class PropertyResult(BaseModel):
    id: int
    url: Optional[str]
    address: Optional[str]
    city: Optional[str]
    district: Optional[str]
    price: Optional[float]
    size_m2: Optional[float]
    disposition: Optional[str]
    construction_type: Optional[str]
    energy_class: Optional[str]
    year_built: Optional[int]
    floor: Optional[int]
    has_elevator: Optional[bool] = None
    ownership: Optional[str] = None
    building_revitalized: Optional[bool] = None
    service_charge: Optional[float] = None
    svl_risk: Optional[str] = None
    locality_tier: Optional[int] = None
    city_stigma: Optional[bool] = None

    scores: ScoreBreakdown
    estimated_rent: Optional[float]
    gross_yield_pct: Optional[float]
    price_per_m2: Optional[float]

    summary: str
    red_flags: list[str]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PropertyDetail(BaseModel):
    """Full property record as stored in DB, with recomputed summary/red_flags and financial calcs."""
    id: int
    url: Optional[str]
    address: Optional[str]
    city: Optional[str]
    district: Optional[str]
    price: Optional[float]
    size_m2: Optional[float]
    disposition: Optional[str]
    construction_type: Optional[str]
    energy_class: Optional[str]
    year_built: Optional[int]
    floor: Optional[int]
    has_elevator: Optional[bool] = None
    ownership: Optional[str] = None
    building_revitalized: Optional[bool] = None
    service_charge: Optional[float] = None
    svl_risk: Optional[str] = None
    locality_tier: Optional[int] = None
    city_stigma: Optional[bool] = None
    kraj: Optional[str] = None          # uloženo v DB při insertu (z CITY_TO_REGION)

    score_total: Optional[float]
    score_yield: Optional[float]
    score_demographic: Optional[float]
    score_economic: Optional[float]
    score_quality: Optional[float]
    score_liquidity: Optional[float]

    estimated_rent: Optional[float]
    gross_yield_pct: Optional[float]
    price_per_m2: Optional[float]

    # Finanční kalkulace (computed, neukládají se do DB)
    collateral_value: Optional[float] = None    # zástavní hodnota
    max_mortgage: Optional[float] = None        # max hypotéka (80 % LTV)
    net_yield_pct: Optional[float] = None       # čistý výnos %
    monthly_cashflow: Optional[float] = None    # měsíční cash flow

    # Cenový benchmark (z price_benchmarks tabulky)
    market_avg_price_m2: Optional[float] = None     # průměrná cena/m² v dané lokalitě
    price_vs_market_pct: Optional[float] = None     # rozdíl oproti průměru v %; záporné = pod průměrem
    benchmark_label: Optional[str] = None           # popis benchmarku, např. "Brno / 3+kk (n=142)"

    summary: str
    red_flags: list[str]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BatchInput(BaseModel):
    url: str                      # Sreality search URL


class BatchResult(BaseModel):
    total_found: int              # raw Sreality region result_size (not shown in UI)
    total_matching: int = 0       # after GPS/bbox filter (what was actually collected)
    total_scraped: int            # successfully fetched detail pages
    total_saved: int              # scored + saved to DB
    total_skipped: int = 0        # already in DB, skipped
    properties: list["PropertyListItem"]
    errors: list[str]


class PropertyListItem(BaseModel):
    id: int
    url: Optional[str]
    address: Optional[str]
    city: Optional[str]
    price: Optional[float]
    size_m2: Optional[float]
    disposition: Optional[str]
    score_total: Optional[float]
    gross_yield_pct: Optional[float]
    locality_tier: Optional[int] = None
    energy_class: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
