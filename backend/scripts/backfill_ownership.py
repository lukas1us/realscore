"""
Backfill ownership pro existující záznamy v DB.

Postup:
  1. Najde všechny záznamy kde ownership IS NULL
  2. Pro Sreality: extrahuje vlastnictví z uloženého raw_data["items"]
  3. Aktualizuje ownership, score_liquidity a score_total

Spuštění:
  python -m backend.scripts.backfill_ownership
  python -m backend.scripts.backfill_ownership --dry-run   # jen zobrazí, neuloží
"""

import argparse
import sys
from sqlalchemy.orm import Session

from backend.database import SessionLocal
from backend.models import Property
from backend.scrapers.constants import parse_ownership
from backend.services.scoring import score_ownership, WEIGHTS


def _extract_ownership_from_raw(raw_data: dict | None, url: str | None) -> str | None:
    """Extrahuje ownership z uloženého raw_data dle portálu."""
    if not raw_data:
        return None

    url_low = (url or "").lower()

    if "sreality" in url_low:
        # raw_data je plný Sreality API response — items je seznam diktů
        items = raw_data.get("items", [])
        for item in items:
            if item.get("name", "").lower() in ("vlastnictví", "vlastnictvi"):
                vals = item.get("value", [])
                raw_val = str(vals[0]) if isinstance(vals, list) and vals else str(vals) if vals else None
                if raw_val:
                    return parse_ownership(raw_val)

    # Bezrealitky a iDNES ukládají jen {"title": ..., "url": ...} — nelze zpětně extrahovat
    return None


def _recalculate_score_total(row: Property, new_score_liquidity: float) -> float:
    """Přepočítá score_total s novým score_liquidity, ostatní dimenze zachová."""
    s_locality  = row.score_demographic or 60.0
    s_penb      = row.score_economic    or 50.0
    s_physical  = row.score_quality     or 50.0
    s_yield     = row.score_yield       or 0.0

    return round(
        WEIGHTS["locality"]  * s_locality
        + WEIGHTS["penb"]    * s_penb
        + WEIGHTS["ownership"] * new_score_liquidity
        + WEIGHTS["physical"] * s_physical
        + WEIGHTS["yield"]   * s_yield,
        1,
    )


def run(dry_run: bool = False) -> None:
    db: Session = SessionLocal()
    try:
        rows = db.query(Property).filter(Property.ownership.is_(None)).all()
        print(f"Záznamy bez ownership: {len(rows)}")

        updated = 0
        skipped = 0

        for row in rows:
            ownership = _extract_ownership_from_raw(row.raw_data, row.url)
            if ownership is None:
                skipped += 1
                continue

            new_score_liquidity = round(score_ownership(ownership), 1)
            new_score_total = _recalculate_score_total(row, new_score_liquidity)

            print(
                f"  id={row.id:>6}  {(row.url or '')[:60]:<60}"
                f"  ownership={ownership:<16}"
                f"  score_liquidity: {row.score_liquidity or 0:.0f} → {new_score_liquidity:.0f}"
                f"  score_total: {row.score_total or 0:.0f} → {new_score_total:.0f}"
            )

            if not dry_run:
                row.ownership = ownership
                row.score_liquidity = new_score_liquidity
                row.score_total = new_score_total
                updated += 1

        if not dry_run:
            db.commit()
            print(f"\nHotovo: aktualizováno {updated}, přeskočeno {skipped} (bez raw_data nebo jiný portál).")
        else:
            print(f"\n[DRY RUN] Bylo by aktualizováno: {len(rows) - skipped}, přeskočeno: {skipped}.")
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill ownership z raw_data.")
    parser.add_argument("--dry-run", action="store_true", help="Jen zobrazí, neuloží do DB")
    args = parser.parse_args()
    run(dry_run=args.dry_run)
