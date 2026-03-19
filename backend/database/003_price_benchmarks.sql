-- Migration 003: price_benchmarks table
-- Stores avg/median price per m² aggregated by city + disposition.
-- Bootstrap: populated from existing properties data on first run.

CREATE TABLE IF NOT EXISTS price_benchmarks (
    id              SERIAL PRIMARY KEY,
    city            VARCHAR NOT NULL,   -- normalized from district (e.g. "Brno", "Praha 4")
    disposition     VARCHAR,            -- '2+1', '3+kk', etc.; NULL = all dispositions combined
    avg_price_m2    FLOAT NOT NULL,
    median_price_m2 FLOAT NOT NULL,
    sample_size     INTEGER NOT NULL,
    updated_at      TIMESTAMP DEFAULT NOW(),
    UNIQUE (city, disposition)
);

-- Bootstrap: compute benchmarks from existing properties.
-- City normalization: take the part of district before " - " (e.g. "Brno - Žebětín" → "Brno").
-- Minimum sample size: 3 properties per group.

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
        updated_at      = NOW();

-- City-level aggregates (NULL disposition = all types combined).
-- ON CONFLICT nefunguje pro NULL v UNIQUE constraintu → DELETE + INSERT.
DELETE FROM price_benchmarks WHERE disposition IS NULL;

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
HAVING COUNT(*) >= 3;

-- Verification query (run manually):
-- SELECT COUNT(*) FROM price_benchmarks;
-- SELECT * FROM price_benchmarks ORDER BY sample_size DESC LIMIT 20;
