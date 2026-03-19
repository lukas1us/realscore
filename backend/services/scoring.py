"""
RealScore CZ – scoring engine v2.

Scoring model (5 dimenzí, vážené):
  Lokalita / SVL čistota   40 %  (score_demographic)
  PENB / Energetická třída 20 %  (score_economic)
  Vlastnictví OV/DV        15 %  (score_liquidity)
  Fyzické parametry        15 %  (score_quality)
  Výnosnost nájmu          10 %  (score_yield)

Pozn.: Názvy DB sloupců jsou zachovány z v1 (score_demographic, score_economic,
score_liquidity) ale jejich sémantika se změnila — viz komentáře u sloupců v models.py.
"""

from __future__ import annotations

import logging
import math
import statistics
from datetime import datetime
from typing import Optional

from backend.scrapers.sreality import scrape_rental_estimates

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Váhy scoring modelu
# ---------------------------------------------------------------------------

WEIGHTS = {
    "locality":   0.40,   # lokalita tier + SVL čistota
    "penb":       0.20,   # PENB / energetická třída
    "ownership":  0.15,   # vlastnictví OV vs DV
    "physical":   0.15,   # fyzické parametry (konstrukce, podlaží, výtah, revitalizace)
    "yield":      0.10,   # výnosnost nájmu
}

RED_FLAG_THRESHOLD = 40

# Města se systémovou stigmatizací zástavní hodnoty
# (banky i trh uplatňují haircut i v jinak dobrých čtvrtích)
STIGMATIZED_CITIES = {
    "Most", "Chomutov", "Litvínov", "Jirkov", "Klášterec nad Ohří",
    "Kadaň", "Sokolov", "Kraslice", "Ostrov", "Aš",
}


# ---------------------------------------------------------------------------
# Dimenze 1: Lokalita / SVL čistota (→ score_demographic v DB)
# ---------------------------------------------------------------------------

def score_locality_svl(
    svl_risk: Optional[str],
    locality_tier: Optional[int],
    city_stigma: Optional[bool],
) -> float:
    """
    Zástavní hodnota + investiční atraktivita lokality.

    Lokalita tier (báze skóre):
        1 (dobrá zástavní hodnota)    → 90
        2 (průměrná)                  → 60
        3 (problematická, nízká ZH)   → 25
        unknown                       → 60 (neutrální)

    SVL penalizace:
        "direct"    → -50 (sociálně vyloučená lokalita = bankám nepůjčují)
        "proximity" → -20 (v blízkosti SVL)
        "none"      → bez penalizace

    Celoměstská stigmatizace (city_stigma):
        True        → -10 (systémový haircut banky i trhu)
    """
    # Báze dle locality tieru
    if locality_tier == 1:
        base = 90.0
    elif locality_tier == 2:
        base = 60.0
    elif locality_tier == 3:
        base = 25.0
    else:
        base = 60.0  # neutrální, pokud není zadáno

    # SVL penalizace
    if svl_risk == "direct":
        base -= 50.0
    elif svl_risk == "proximity":
        base -= 20.0

    # Celoměstská stigmatizace
    if city_stigma:
        base -= 10.0

    return max(0.0, min(100.0, base))


# ---------------------------------------------------------------------------
# Dimenze 2: PENB / Energetická třída (→ score_economic v DB)
# ---------------------------------------------------------------------------

_PENB_SCORES = {
    "A": 100.0,
    "B": 85.0,
    "C": 70.0,
    "D": 50.0,
    "E": 30.0,
    "F": 10.0,
    "G": 0.0,
}


def score_penb(energy_class: Optional[str]) -> float:
    """
    PENB (průkaz energetické náročnosti budovy).

    F/G = penalizace bankou (nižší zástavní hodnota) i nájemci (vysoké provozní náklady).
    Neznámá třída → neutrální (50).
    """
    if not energy_class:
        return 50.0
    return _PENB_SCORES.get(energy_class.upper(), 50.0)


# ---------------------------------------------------------------------------
# Dimenze 3: Vlastnictví OV/DV (→ score_liquidity v DB)
# ---------------------------------------------------------------------------

def score_ownership(ownership: Optional[str]) -> float:
    """
    Typ vlastnictví z pohledu zástavitelnosti a likvidity.

    OV (osobní vlastnictví):   100 — plná zástavní hodnota, volně prodejné
    DV (družstevní):            40 — banka diskontuje, těžší prodat, pomalejší převod
    DV bez možnosti převodu:    10 — banky odmítají zástavit, extrémně nízká likvidita
    Neznámé:                    60 — mírně pod OV, ale nepenalizujeme bez informace
    """
    if ownership == "OV":
        return 100.0
    if ownership == "DV":
        return 40.0
    if ownership == "DV_no_transfer":
        return 10.0
    return 60.0  # neznámé → mírně podprůměrné


# ---------------------------------------------------------------------------
# Dimenze 4: Fyzické parametry (→ score_quality v DB)
# ---------------------------------------------------------------------------

def score_physical(
    construction_type: Optional[str],
    floor: Optional[int],
    has_elevator: Optional[bool],
    building_revitalized: Optional[bool],
) -> float:
    """
    Fyzická kvalita nemovitosti pro investici do pronájmu.

    Složení:
        Typ konstrukce      40 % (cihla > panel)
        Podlaží + výtah     35 % (přízemí OK, vysoká patra bez výtahu špatná)
        Revitalizace domu   25 % (revitalizovaný panel >> nerevitalizovaný)
    """
    # --- Konstrukce (40 %) ---
    if not construction_type:
        c_score = 50.0
    else:
        low = construction_type.lower()
        if "cihla" in low:
            c_score = 100.0
        elif "nizkoenergetick" in low:
            c_score = 95.0
        elif "drevostavba" in low:
            c_score = 80.0
        elif "smisen" in low:
            c_score = 60.0
        elif "montovan" in low:
            c_score = 40.0
        elif "panel" in low:
            c_score = 30.0
        else:
            c_score = 50.0

    # --- Podlaží + výtah (35 %) ---
    floor_int = floor or 0
    if floor_int == 0 or floor_int == 1:
        # Přízemí/1. patro: snadno dostupné, ale méně preferované nájemci
        f_score = 60.0
    elif floor_int <= 5:
        f_score = 90.0  # ideální patra pro pronájem
    elif floor_int <= 8:
        f_score = 70.0
    else:
        f_score = 50.0  # velmi vysoké patro

    if has_elevator is False and floor_int > 2:
        # Bez výtahu na vyšším podlaží = problém pro starší nájemce
        f_score = max(0.0, f_score - 25.0)
    elif has_elevator is True:
        f_score = min(100.0, f_score + 10.0)

    # --- Revitalizace (25 %) ---
    if building_revitalized is True:
        r_score = 100.0
    elif building_revitalized is False:
        r_score = 30.0  # nerevitalizovaný → vyšší fond oprav, nižší atraktivita
    else:
        r_score = 60.0  # neznámé

    return max(0.0, min(100.0,
        0.40 * c_score + 0.35 * f_score + 0.25 * r_score
    ))


# ---------------------------------------------------------------------------
# Dimenze 5: Výnosnost nájmu (→ score_yield v DB)
# ---------------------------------------------------------------------------

def score_rental_yield(
    price: Optional[float],
    city: Optional[str],
    disposition: Optional[str],
    size_m2: Optional[float],
) -> tuple[float, Optional[float], Optional[float]]:
    """
    Returns (score 0–100, estimated_monthly_rent, gross_yield_pct).

    Gross yield = (roční nájem / kupní cena) × 100.
    Stupnice skóre:
        >= 8 %  → 100
        6–8 %   → 60–100
        4–6 %   → 30–60
        < 4 %   → 0–30
    """
    estimated_rent: Optional[float] = None
    gross_yield_pct: Optional[float] = None

    if not price or price <= 0:
        return 0.0, None, None

    # Pokus o načtení srovnatelných nájmů ze Sreality
    rents: list[float] = []
    if city and disposition:
        try:
            rents = scrape_rental_estimates(city, disposition)
        except Exception as exc:
            logger.warning("Rental scrape failed: %s", exc)

    if rents:
        estimated_rent = statistics.median(rents)
    elif size_m2 and size_m2 > 0:
        # Záložní odhad: průměr dle m² (CZK/měsíc)
        # Praha ~350 Kč/m², Brno ~300, regionální města ~200
        RENT_PER_M2_DEFAULT = 250.0
        estimated_rent = size_m2 * RENT_PER_M2_DEFAULT
    else:
        return 20.0, None, None

    gross_yield_pct = (estimated_rent * 12 / price) * 100
    score = _yield_to_score(gross_yield_pct)
    return score, estimated_rent, gross_yield_pct


def _yield_to_score(yield_pct: float) -> float:
    if yield_pct >= 8.0:
        return 100.0
    if yield_pct >= 6.0:
        return 60.0 + (yield_pct - 6.0) / 2.0 * 40.0
    if yield_pct >= 4.0:
        return 30.0 + (yield_pct - 4.0) / 2.0 * 30.0
    if yield_pct >= 2.0:
        return (yield_pct - 2.0) / 2.0 * 30.0
    return 0.0


# ---------------------------------------------------------------------------
# Finanční kalkulace
# ---------------------------------------------------------------------------

def collateral_coefficient(
    locality_tier: Optional[int],
    svl_risk: Optional[str],
    city_stigma: Optional[bool],
) -> float:
    """
    Odhadovaný koeficient zástavní hodnoty (ZH = kupní cena × koeficient).

    Orientační hodnoty dle lokality:
        Tier 1, bez SVL, bez stigmy:  0.95
        Tier 2, bez SVL, bez stigmy:  0.85
        Tier 3, bez SVL, bez stigmy:  0.75
        SVL proximity:                max(base, 0.75) → base - 0.08
        SVL direct:                   max(base, 0.60) → min(base, 0.58)
        City stigma:                  -0.05
    """
    if locality_tier == 1:
        base = 0.95
    elif locality_tier == 3:
        base = 0.75
    else:
        base = 0.85  # tier 2 nebo neznámý

    if svl_risk == "direct":
        base = min(base, 0.58)
    elif svl_risk == "proximity":
        base = min(base, 0.77)

    if city_stigma:
        base -= 0.05

    return max(0.50, min(0.98, base))


def monthly_mortgage_payment(
    principal: float,
    annual_rate_pct: float = 5.0,
    years: int = 30,
) -> float:
    """Splátka hypotéky (annuity) v CZK/měsíc."""
    r = annual_rate_pct / 100.0 / 12.0
    n = years * 12
    if r == 0:
        return principal / n
    return principal * (r * (1 + r) ** n) / ((1 + r) ** n - 1)


def compute_financial(
    price: Optional[float],
    estimated_rent: Optional[float],
    service_charge: Optional[float],
    locality_tier: Optional[int],
    svl_risk: Optional[str],
    city_stigma: Optional[bool],
    gross_yield_pct: Optional[float],
) -> dict:
    """
    Finanční kalkulace pro detail nemovitosti.

    Vrací: collateral_value, max_mortgage, net_yield_pct, monthly_cashflow.
    """
    result: dict = {
        "collateral_value": None,
        "max_mortgage": None,
        "net_yield_pct": None,
        "monthly_cashflow": None,
    }

    if not price or price <= 0:
        return result

    koef = collateral_coefficient(locality_tier, svl_risk, city_stigma)
    result["collateral_value"] = round(price * koef)
    result["max_mortgage"] = round(result["collateral_value"] * 0.80)

    if estimated_rent and estimated_rent > 0:
        # Čistý nájem: odečíst ~28 % (pojištění + správa + rezerva na opravy)
        net_monthly_rent = estimated_rent * 0.72
        if service_charge:
            # Fond oprav už je v estimated_rent nezahrnutý → odečteme zvlášť
            net_monthly_rent -= service_charge

        result["net_yield_pct"] = round(net_monthly_rent * 12 / price * 100, 2)

        # Cash flow = čistý nájem - splátka hypotéky
        mortgage = monthly_mortgage_payment(result["max_mortgage"])
        result["monthly_cashflow"] = round(net_monthly_rent - mortgage)

    return result


# ---------------------------------------------------------------------------
# Hlavní compose funkce
# ---------------------------------------------------------------------------

def compute_scores(prop: dict) -> dict:
    """
    Vypočítá všechny dílčí skóre a celkové kompozitní skóre.

    `prop` je dict s klíči odpovídajícími polím PropertyInput.

    Vrací dict:
        score_yield, score_demographic (=lokalita), score_economic (=PENB),
        score_quality (=fyzické), score_liquidity (=vlastnictví),
        score_total, estimated_rent, gross_yield_pct, summary, red_flags
    """
    price = prop.get("price")
    city = prop.get("city")
    disposition = prop.get("disposition")
    size_m2 = prop.get("size_m2")
    construction_type = prop.get("construction_type")
    energy_class = prop.get("energy_class")
    floor = prop.get("floor")
    has_elevator = prop.get("has_elevator")
    building_revitalized = prop.get("building_revitalized")
    ownership = prop.get("ownership")
    svl_risk = prop.get("svl_risk")
    locality_tier = prop.get("locality_tier")
    # city_stigma: auto-compute z názvu města pokud není explicitně zadáno
    city_stigma = prop.get("city_stigma")
    if city_stigma is None and city:
        city_stigma = city.strip() in STIGMATIZED_CITIES

    # --- Výpočet dimenzí ---
    s_locality = score_locality_svl(svl_risk, locality_tier, city_stigma)
    s_penb = score_penb(energy_class)
    s_ownership = score_ownership(ownership)
    s_physical = score_physical(construction_type, floor, has_elevator, building_revitalized)
    s_yield, estimated_rent, gross_yield_pct = score_rental_yield(price, city, disposition, size_m2)

    # --- Celkové skóre ---
    score_total = (
        WEIGHTS["locality"] * s_locality
        + WEIGHTS["penb"] * s_penb
        + WEIGHTS["ownership"] * s_ownership
        + WEIGHTS["physical"] * s_physical
        + WEIGHTS["yield"] * s_yield
    )

    scores = {
        # Mapování: nová dimenze → původní DB sloupec
        "score_yield": round(s_yield, 1),
        "score_demographic": round(s_locality, 1),   # ← lokalita / SVL
        "score_economic": round(s_penb, 1),           # ← PENB
        "score_quality": round(s_physical, 1),        # ← fyzické parametry
        "score_liquidity": round(s_ownership, 1),     # ← vlastnictví OV/DV
        "score_total": round(score_total, 1),
        "estimated_rent": round(estimated_rent) if estimated_rent else None,
        "gross_yield_pct": round(gross_yield_pct, 2) if gross_yield_pct else None,
        # Předat city_stigma pro uložení do DB
        "city_stigma": city_stigma,
    }

    scores["red_flags"] = _build_red_flags(scores, prop)
    scores["summary"] = _build_summary(scores, prop)
    return scores


# ---------------------------------------------------------------------------
# Červené vlajky a textové hodnocení
# ---------------------------------------------------------------------------

_SCORE_LABELS = {
    "score_demographic": "lokalita / SVL čistota",
    "score_economic": "energetická třída (PENB)",
    "score_liquidity": "typ vlastnictví",
    "score_quality": "fyzické parametry",
    "score_yield": "výnosnost nájmu",
}


def _build_red_flags(scores: dict, prop: dict) -> list[str]:
    flags = []

    # Nízká skóre dimenzí
    for key, label in _SCORE_LABELS.items():
        val = scores.get(key, 100)
        if val < RED_FLAG_THRESHOLD:
            flags.append(f"Nízké skóre: {label} ({val:.0f}/100)")

    # Specifická varování
    ownership = prop.get("ownership")
    if ownership == "DV_no_transfer":
        flags.append("Družstevní vlastnictví BEZ možnosti převodu — nelze zástavit, banka odmítne")
    elif ownership == "DV":
        flags.append("Družstevní vlastnictví — banka diskontuje zástavní hodnotu, pomalejší prodej")

    svl_risk = prop.get("svl_risk")
    if svl_risk == "direct":
        flags.append("SVL riziko: přímá sociálně vyloučená lokalita — banky odmítají zástavit")
    elif svl_risk == "proximity":
        flags.append("SVL riziko: blízkost sociálně vyloučené lokality — zástavní hodnota nižší")

    city_stigma = prop.get("city_stigma") or scores.get("city_stigma")
    if city_stigma:
        flags.append("Celoměstská stigmatizace — banka uplatňuje plošný haircut zástavní hodnoty")

    energy = prop.get("energy_class", "")
    if energy in ("F", "G"):
        flags.append(f"PENB třída {energy} — banky diskontují zástavní hodnotu, nájemci platí vysoké energie")

    if prop.get("price") and prop.get("size_m2"):
        price_per_m2 = prop["price"] / prop["size_m2"]
        if price_per_m2 > 150_000:
            flags.append(f"Velmi vysoká cena za m² ({price_per_m2:,.0f} Kč/m²)")

    return flags


def _build_summary(scores: dict, prop: dict) -> str:
    total = scores["score_total"]
    city = prop.get("city", "neznámá lokalita")
    disposition = prop.get("disposition", "")
    ownership = prop.get("ownership")
    gross_yield = scores.get("gross_yield_pct")
    locality_tier = prop.get("locality_tier")

    if total >= 70:
        quality = "nadprůměrnou investiční příležitostí"
    elif total >= 50:
        quality = "průměrnou investicí s určitými riziky"
    else:
        quality = "investicí s výraznými riziky"

    parts = [
        f"Nemovitost v lokalitě {city}{' (' + disposition + ')' if disposition else ''} "
        f"je {quality} s celkovým skóre {total:.0f}/100."
    ]

    # Lokalita
    if locality_tier == 1:
        parts.append("Lokalita s dobrou zástavní hodnotou — vhodná pro hypotéku.")
    elif locality_tier == 3:
        parts.append("Problematická lokalita — nízká zástavní hodnota, obtížné financování.")

    # Výnos
    if gross_yield:
        if gross_yield >= 6:
            parts.append(f"Odhadovaný hrubý výnos {gross_yield:.1f} % je atraktivní pro investora.")
        elif gross_yield >= 4:
            parts.append(f"Odhadovaný hrubý výnos {gross_yield:.1f} % je průměrný.")
        else:
            parts.append(f"Hrubý výnos {gross_yield:.1f} % je pod průměrem trhu.")

    return " ".join(parts[:3])  # max 3 věty
