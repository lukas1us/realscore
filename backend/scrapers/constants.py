"""
Shared constants used across multiple scrapers.

Centralised here to avoid divergence between bezrealitky.py, idnes.py,
sreality.py, sreality_search.py, and market.py.
"""

from typing import Optional

# ---------------------------------------------------------------------------
# HTTP headers
# ---------------------------------------------------------------------------

# For Sreality JSON API endpoints (Accept: application/json)
HEADERS_API: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Referer": "https://www.sreality.cz/",
}

# For HTML scrapers (Bezrealitky, iDNES)
HEADERS_HTML: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "cs-CZ,cs;q=0.9",
}

# ---------------------------------------------------------------------------
# Construction type normalisation
# ---------------------------------------------------------------------------

# Maps raw strings (Czech, with diacritics or without) to canonical values
# used throughout the app and the scoring engine.
CONSTRUCTION_KEYWORDS: dict[str, str] = {
    "panel":            "panel",
    "panelový":         "panel",
    "cihla":            "cihla",
    "cihlový":          "cihla",
    "smíšený":          "smiseny",
    "smiseny":          "smiseny",
    "nízkoenergetický": "nizkoenergeticky",
    "dřevostavba":      "drevostavba",
    "montovaný":        "montovany",
}

# ---------------------------------------------------------------------------
# Disposition → Sreality category_sub_cb codes
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Ownership normalisation
# ---------------------------------------------------------------------------

def parse_ownership(raw: str) -> Optional[str]:
    """
    Normalise free-text ownership label to "OV" | "DV" | "DV_no_transfer".

    Sreality: "Vlastnictví" → "Osobní" / "Družstevní"
    Bezrealitky / iDNES: similar Czech labels in parameter tables.
    """
    low = raw.lower()
    if "osobní" in low or "osobni" in low:
        return "OV"
    if "družstevní" in low or "druzstevni" in low or "družstev" in low:
        if "bez" in low and ("převod" in low or "prevod" in low):
            return "DV_no_transfer"
        return "DV"
    return None


# ---------------------------------------------------------------------------
# Disposition → Sreality category_sub_cb codes
# ---------------------------------------------------------------------------

DISP_TO_CODE: dict[str, int] = {
    "1+kk": 2,  "1+1": 3,
    "2+kk": 4,  "2+1": 5,
    "3+kk": 6,  "3+1": 7,
    "4+kk": 8,  "4+1": 9,
    "5+kk": 10, "5+1": 11,
    "6+":   12,
}
