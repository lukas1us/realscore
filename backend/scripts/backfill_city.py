"""
Backfill city pro existující záznamy v DB.

Problém: Sreality locality má formát "Ulice, Město, Kraj" — původní parser
ukládal Ulici do pole city a Město do district.  Po opravě parseru
(commit: fix Sreality city extraction) tato skript přepíše city
z uloženého raw_data["locality"] pomocí opravené logiky.

Bezie tím se field `district` nijak nemění (benchmark lookup zůstane funkční).

Spuštění:
  python -m backend.scripts.backfill_city
  python -m backend.scripts.backfill_city --dry-run   # jen zobrazí, neuloží
"""

import argparse
import re
from typing import Optional

from sqlalchemy.orm import Session

from backend.database import SessionLocal
from backend.models import Property
from backend.utils.regions import CITY_TO_REGION


def _to_str(val) -> Optional[str]:
    """Rozbalí Sreality locality — může být string, dict {"value": ...} nebo list."""
    if val is None:
        return None
    if isinstance(val, str):
        return val
    if isinstance(val, dict):
        return _to_str(val.get("value"))
    if isinstance(val, list) and val:
        return _to_str(val[0])
    return None


def _extract_city(locality) -> Optional[str]:
    """Re-extrahuje municipality z locality stringu (stejná logika jako opravený scraper)."""
    locality = _to_str(locality)
    if not locality:
        return None

    parts = [p.strip() for p in locality.split(",")]

    # Praha special case
    praha_idx = next(
        (i for i, p in enumerate(parts) if re.match(r"^Praha", p, re.IGNORECASE)),
        None,
    )
    if praha_idx is not None and praha_idx > 0:
        return "Praha"
    elif len(parts) >= 3:
        # "Street, Municipality, Region" → municipality je druhý od konce
        return parts[-2]
    elif len(parts) == 2:
        # "Město, Ústecký kraj" → první část je město
        # "Ulice, Město"        → druhá část je město
        if re.search(r"\bkraj\b", parts[-1], re.IGNORECASE):
            return parts[0]
        return parts[-1]
    else:
        return parts[0] if parts else None


def _looks_like_street(city: str | None) -> bool:
    """Heuristika: vrátí True pokud city vypadá jako ulice, ne obec."""
    if not city:
        return False
    # Pokud je v CITY_TO_REGION nebo začíná "Praha" → není ulice
    if re.match(r"^Praha\b", city, re.IGNORECASE):
        return False
    if city in CITY_TO_REGION:
        return False
    return True


def run(dry_run: bool = False) -> None:
    db: Session = SessionLocal()
    try:
        # Zpracuj jen Sreality záznamy (mají raw_data s locality)
        rows = (
            db.query(Property)
            .filter(Property.url.ilike("%sreality%"))
            .all()
        )
        print(f"Sreality záznamy celkem: {len(rows)}")

        updated = 0
        skipped = 0

        for row in rows:
            if not row.raw_data:
                skipped += 1
                continue

            locality = row.raw_data.get("locality")
            if not locality:
                skipped += 1
                continue

            new_city = _extract_city(locality)
            if new_city is None or new_city == row.city:
                skipped += 1
                continue

            print(
                f"  id={row.id:>6}  city: {(row.city or 'None'):<30} → {new_city:<30}"
                f"  locality: {(_to_str(locality) or '')[:60]}"
            )

            if not dry_run:
                row.city = new_city
                updated += 1

        if not dry_run:
            db.commit()
            print(f"\nHotovo: aktualizováno {updated}, přeskočeno {skipped}.")
        else:
            print(f"\n[DRY RUN] Bylo by aktualizováno: {updated}, přeskočeno: {skipped}.")
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill city z raw_data locality.")
    parser.add_argument("--dry-run", action="store_true", help="Jen zobrazí, neuloží do DB")
    args = parser.parse_args()
    run(dry_run=args.dry_run)
