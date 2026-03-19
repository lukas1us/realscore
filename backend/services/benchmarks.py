"""
Price benchmark helpers.

Benchmarks are stored in the `price_benchmarks` table and computed by
aggregating price/m² from the `properties` table (no new scraping).

Lookup strategy for get_benchmark():
  1. Match city + disposition  → specific benchmark
  2. Fallback to city + NULL disposition  → city-level average (all types)
"""

import re
import logging
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.models import PriceBenchmark

logger = logging.getLogger(__name__)


def _normalize_city(district: str | None) -> str | None:
    """Normalize district value to benchmark city key.

    'Brno - Žebětín' → 'Brno'
    'Praha 4 - Krč'  → 'Praha 4'
    'Kyjov'          → 'Kyjov'
    """
    if not district:
        return None
    return district.split(" - ")[0].strip() or None


def get_benchmark(db: Session, district: str | None, disposition: str | None) -> dict | None:
    """Return benchmark for the given city (normalized from district) and disposition.

    Falls back to city-wide benchmark (NULL disposition) when no specific one exists.
    Returns None if no benchmark is available at all.
    """
    city = _normalize_city(district)
    if not city:
        return None

    # 1. Specific: city + disposition
    if disposition:
        row = (
            db.query(PriceBenchmark)
            .filter(PriceBenchmark.city == city, PriceBenchmark.disposition == disposition)
            .first()
        )
        if row:
            return {
                "city": city,
                "disposition": disposition,
                "avg_price_m2": row.avg_price_m2,
                "median_price_m2": row.median_price_m2,
                "sample_size": row.sample_size,
            }

    # 2. Fallback: city + all types
    row = (
        db.query(PriceBenchmark)
        .filter(PriceBenchmark.city == city, PriceBenchmark.disposition.is_(None))
        .first()
    )
    if row:
        return {
            "city": city,
            "disposition": None,
            "avg_price_m2": row.avg_price_m2,
            "median_price_m2": row.median_price_m2,
            "sample_size": row.sample_size,
        }

    return None


def refresh_benchmarks(db: Session) -> int:
    """Recompute all benchmarks from current properties data.

    Uses raw SQL for PERCENTILE_CONT which SQLAlchemy ORM doesn't support natively.
    Returns the number of benchmark rows upserted.
    """
    upsert_sql = text("""
        INSERT INTO price_benchmarks (city, disposition, avg_price_m2, median_price_m2, sample_size, updated_at)
        SELECT
            SPLIT_PART(district, ' - ', 1)                          AS city,
            disposition,
            AVG(price / size_m2)                                    AS avg_price_m2,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY price / size_m2) AS median_price_m2,
            COUNT(*)                                                AS sample_size,
            NOW()                                                   AS updated_at
        FROM properties
        WHERE
            price IS NOT NULL
            AND size_m2 IS NOT NULL
            AND size_m2 > 0
            AND district IS NOT NULL
            AND TRIM(district) <> ''
        GROUP BY SPLIT_PART(district, ' - ', 1), disposition
        HAVING COUNT(*) >= 3
        ON CONFLICT (city, disposition) DO UPDATE
            SET avg_price_m2    = EXCLUDED.avg_price_m2,
                median_price_m2 = EXCLUDED.median_price_m2,
                sample_size     = EXCLUDED.sample_size,
                updated_at      = NOW()
    """)

    # City-wide (NULL disposition): ON CONFLICT nefunguje pro NULL v UNIQUE constraintu
    # (PostgreSQL nepovažuje NULL = NULL), proto použijeme DELETE + INSERT.
    delete_city_sql = text("DELETE FROM price_benchmarks WHERE disposition IS NULL")

    insert_city_sql = text("""
        INSERT INTO price_benchmarks (city, disposition, avg_price_m2, median_price_m2, sample_size, updated_at)
        SELECT
            SPLIT_PART(district, ' - ', 1)                          AS city,
            NULL                                                    AS disposition,
            AVG(price / size_m2)                                    AS avg_price_m2,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY price / size_m2) AS median_price_m2,
            COUNT(*)                                                AS sample_size,
            NOW()                                                   AS updated_at
        FROM properties
        WHERE
            price IS NOT NULL
            AND size_m2 IS NOT NULL
            AND size_m2 > 0
            AND district IS NOT NULL
            AND TRIM(district) <> ''
        GROUP BY SPLIT_PART(district, ' - ', 1)
        HAVING COUNT(*) >= 3
    """)

    db.execute(upsert_sql)
    db.execute(delete_city_sql)
    db.execute(insert_city_sql)
    db.commit()

    total = db.query(PriceBenchmark).count()
    logger.info("refresh_benchmarks: %d rows in price_benchmarks", total)
    return total
