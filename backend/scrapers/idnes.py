"""
Reality iDNES.cz scraper – HTML-based.

URL pattern:
  https://reality.idnes.cz/detail/prodej/byt/{slug}/{id}/
"""

import re
import logging
from typing import Optional

import httpx
from bs4 import BeautifulSoup, Tag

logger = logging.getLogger(__name__)

from backend.scrapers.constants import HEADERS_HTML as HEADERS, CONSTRUCTION_KEYWORDS, parse_ownership


def _clean_price(text: str) -> Optional[float]:
    digits = re.sub(r"[^\d]", "", text)
    return float(digits) if digits else None


def _parse_construction(raw: str) -> str:
    low = raw.lower()
    for kw, canonical in CONSTRUCTION_KEYWORDS.items():
        if kw in low:
            return canonical
    return raw


def _text(tag: Optional[Tag]) -> str:
    return tag.get_text(" ", strip=True) if tag else ""


def scrape_idnes(url: str) -> dict:
    """
    Scrape a reality.idnes.cz property detail page.
    Raises ValueError on failure.
    """
    logger.info("Fetching iDNES reality: %s", url)

    with httpx.Client(headers=HEADERS, timeout=20, follow_redirects=True) as client:
        resp = client.get(url)

    if resp.status_code != 200:
        raise ValueError(f"iDNES vrátilo status {resp.status_code}")

    soup = BeautifulSoup(resp.text, "lxml")

    # ---- title ----
    title = ""
    h1 = soup.find("h1")
    if h1:
        title = h1.get_text(strip=True)

    # ---- price ----
    price_czk: Optional[float] = None
    # iDNES uses <strong class="...price..."> or <b class="b-detail__price">
    for sel in [
        {"class": re.compile(r"price", re.I)},
        {"class": re.compile(r"b-detail__price", re.I)},
        {"itemprop": "price"},
    ]:
        tag = soup.find(["strong", "b", "span", "p"], attrs=sel)
        if tag:
            price_czk = _clean_price(tag.get_text())
            if price_czk and price_czk > 10_000:
                break

    # ---- disposition ----
    disposition: Optional[str] = None
    disp_match = re.search(r"(\d\+(?:kk|\d))", title, re.IGNORECASE)
    if disp_match:
        disposition = disp_match.group(1).lower()

    # ---- parameters ----
    # iDNES lists params in <table class="params-table"> or <ul class="b-definition-list">
    size_m2: Optional[float] = None
    year_built: Optional[int] = None
    floor: Optional[int] = None
    energy_class: Optional[str] = None
    construction_type: Optional[str] = None
    ownership: Optional[str] = None

    # Strategy: collect all (label, value) pairs from definition lists and tables
    pairs: list[tuple[str, str]] = []

    for dl in soup.find_all("dl"):
        dts = dl.find_all("dt")
        dds = dl.find_all("dd")
        for dt, dd in zip(dts, dds):
            pairs.append((_text(dt).lower(), _text(dd)))

    for row in soup.find_all("tr"):
        cells = row.find_all(["th", "td"])
        if len(cells) >= 2:
            pairs.append((_text(cells[0]).lower(), _text(cells[1])))

    # Also try generic li / span combos used by iDNES
    for li in soup.find_all("li", class_=re.compile(r"param|spec|detail", re.I)):
        text = li.get_text(" ", strip=True)
        if ":" in text:
            label, _, value = text.partition(":")
            pairs.append((label.lower().strip(), value.strip()))

    logger.debug("iDNES param pairs: %s", pairs[:20])

    for label, value in pairs:
        if not size_m2 and ("plocha" in label or "m²" in label or "m2" in label):
            nums = re.findall(r"\d+", value.replace("\xa0", "").replace(" ", ""))
            if nums:
                size_m2 = float(nums[0])

        if not year_built and ("rok" in label and ("výstavby" in label or "kolaudace" in label or "postaven" in label)):
            ym = re.search(r"\d{4}", value)
            if ym:
                year_built = int(ym.group())

        if not floor and ("podlaží" in label or "patro" in label):
            fm = re.search(r"(\d+)", value)
            if fm:
                floor = int(fm.group(1))

        if not energy_class and "energetick" in label:
            em = re.search(r"\b([A-Ga-g])\b", value)
            if em:
                energy_class = em.group(1).upper()

        if not construction_type and ("konstrukce" in label or "typ budovy" in label or "stavba" in label):
            construction_type = _parse_construction(value)

        if not ownership and "vlastnictví" in label:
            parsed = parse_ownership(value)
            if parsed:
                ownership = parsed

    # Fallback: size from title "Prodej bytu 1+1, 38 m²"
    if size_m2 is None:
        m = re.search(r"(\d+)\s*m²", title)
        if m:
            size_m2 = float(m.group(1))

    # ---- location ----
    city: Optional[str] = None
    district: Optional[str] = None
    address: Optional[str] = None

    # Breadcrumb is the most reliable source on iDNES
    breadcrumb = soup.find(class_=re.compile(r"breadcrumb|b-path|navigation", re.I))
    if breadcrumb:
        crumbs = [a.get_text(strip=True) for a in breadcrumb.find_all("a")]
        # Typical: Prodej > Byty > Ústecký kraj > Ústí nad Labem > Střekov
        if crumbs:
            # Last non-empty crumb is the most specific location
            location_parts = [c for c in crumbs if c and c.lower() not in ("reality", "prodej", "byty", "domy")]
            if location_parts:
                city = location_parts[-1]
                if len(location_parts) >= 2:
                    district = location_parts[-2]
                address = ", ".join(location_parts)

    # Fallback: og:description or meta description
    if not city:
        for meta in soup.find_all("meta"):
            content = meta.get("content", "")
            if "Ústí" in content or "Praha" in content or "Brno" in content:
                parts = [p.strip() for p in content.split(",")]
                if parts:
                    city = parts[-1]
                break

    # Fallback: extract city from URL slug
    # e.g. /detail/prodej/byt/bilina-m-svabinskeho/...
    if not city:
        slug_match = re.search(r"/detail/[^/]+/[^/]+/([^/]+)/", url)
        if slug_match:
            slug = slug_match.group(1)
            city = slug.split("-")[0].capitalize()

    logger.info("iDNES parsed: price=%s size=%s disposition=%s city=%s", price_czk, size_m2, disposition, city)

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
