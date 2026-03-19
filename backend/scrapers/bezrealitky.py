"""
Bezrealitky.cz scraper – HTML-based (they block API calls).

Parses property detail pages using BeautifulSoup.
"""

import re
import logging
from typing import Optional
import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

from backend.scrapers.constants import HEADERS_HTML as HEADERS, CONSTRUCTION_KEYWORDS, parse_ownership


def _clean_price(text: str) -> Optional[float]:
    nums = re.sub(r"[^\d]", "", text)
    return float(nums) if nums else None


def _parse_construction(raw: str) -> str:
    low = raw.lower()
    for kw, canonical in CONSTRUCTION_KEYWORDS.items():
        if kw in low:
            return canonical
    return raw


def scrape_bezrealitky(url: str) -> dict:
    """
    Scrape a Bezrealitky property detail page.

    Returns a dict with normalised fields.
    Raises ValueError on failure.
    """
    logger.info("Fetching Bezrealitky: %s", url)

    with httpx.Client(headers=HEADERS, timeout=20, follow_redirects=True) as client:
        resp = client.get(url)

    if resp.status_code != 200:
        raise ValueError(f"Bezrealitky vrátilo status {resp.status_code}")

    soup = BeautifulSoup(resp.text, "lxml")

    # ---- price ----
    price_czk: Optional[float] = None
    price_tag = (
        soup.find("strong", class_=re.compile(r"price", re.I))
        or soup.find("p", class_=re.compile(r"price", re.I))
        or soup.find(attrs={"data-testid": re.compile(r"price", re.I)})
    )
    if price_tag:
        price_czk = _clean_price(price_tag.get_text())
 
    # ---- title / name ----
    title = ""
    h1 = soup.find("h1")
    if h1:
        title = h1.get_text(strip=True)

    # ---- disposition ----
    disposition: Optional[str] = None
    disp_match = re.search(r"(\d\+(?:kk|\d))", title, re.IGNORECASE)
    if disp_match:
        disposition = disp_match.group(1).lower()

    # ---- parameters table ----
    size_m2: Optional[float] = None
    year_built: Optional[int] = None
    floor: Optional[int] = None
    energy_class: Optional[str] = None
    construction_type: Optional[str] = None
    ownership: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None
    address: Optional[str] = None

    # Bezrealitky uses a <dl> / <dt>/<dd> or table with parameter rows
    for row in soup.find_all(["li", "tr", "div"], class_=re.compile(r"param|detail|feature|spec", re.I)):
        text = row.get_text(" ", strip=True).lower()

        if "plocha" in text or "m²" in text or "m2" in text:
            nums = re.findall(r"[\d,]+", text)
            if nums:
                size_m2 = float(nums[0].replace(",", "."))

        if "rok výstavby" in text or "rok kolaudace" in text or "postaven" in text:
            ym = re.search(r"\d{4}", text)
            if ym:
                year_built = int(ym.group())

        if "podlaží" in text or "patro" in text:
            fm = re.search(r"(\d+)\.", text)
            if fm:
                floor = int(fm.group(1))

        if "energetick" in text:
            em = re.search(r"\b([A-Ga-g])\b", row.get_text())
            if em:
                energy_class = em.group(1).upper()

        if "konstrukce" in text or "typ budovy" in text:
            dd = row.find("dd") or row.find("span")
            if dd:
                construction_type = _parse_construction(dd.get_text(strip=True))

        if not ownership and ("vlastnictví" in text or "vlastnictvi" in text):
            parsed = parse_ownership(row.get_text(" ", strip=True))
            if parsed:
                ownership = parsed

    # ---- location ----
    # Try breadcrumb or address block
    breadcrumb = soup.find(class_=re.compile(r"breadcrumb|location|address", re.I))
    if breadcrumb:
        parts = [p.strip() for p in breadcrumb.get_text(",").split(",") if p.strip()]
        if parts:
            address = ", ".join(parts)
            city = parts[-1] if parts else None

    # Fallback: look for structured address in meta tags
    if not city:
        meta_loc = soup.find("meta", property="og:description") or soup.find("meta", attrs={"name": "description"})
        if meta_loc:
            content = meta_loc.get("content", "")
            parts = [p.strip() for p in content.split(",")]
            if len(parts) >= 2:
                city = parts[-1]

    return {
        "url": url,
        "address": address,
        "city": city,
        "district": district,
        "price": price_czk,
        "size_m2": size_m2,
        "disposition": disposition,
        "construction_type": construction_type,
        "energy_class": energy_class,
        "year_built": year_built,
        "floor": floor,
        "ownership": ownership,
        "raw_data": {"title": title, "url": url},
    }
