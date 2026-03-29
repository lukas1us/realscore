-- Migration 000: Complete database initialization
-- Run this on a FRESH server INSTEAD of migrations 002 and 003.
-- Existing installations should run 002 and 003 separately.
--
-- Usage (as superuser, e.g. postgres):
--   psql -U postgres -f backend/database/000_initialization.sql
--
-- Or step by step:
--   psql -U postgres -c "CREATE DATABASE \"realscoreCZ\";"
--   psql $DATABASE_URL -f backend/database/000_initialization.sql

-- ---------------------------------------------------------------------------
-- Create database (skip if it already exists)
-- ---------------------------------------------------------------------------
SELECT 'CREATE DATABASE "realscoreCZ"'
WHERE NOT EXISTS (
    SELECT FROM pg_database WHERE datname = 'realscoreCZ'
)\gexec

\connect "realscoreCZ"

-- ---------------------------------------------------------------------------
-- Table: properties
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS properties (
    id                  SERIAL PRIMARY KEY,
    url                 VARCHAR,
    address             VARCHAR,
    city                VARCHAR,
    district            VARCHAR,

    price               FLOAT,
    size_m2             FLOAT,
    disposition         VARCHAR,
    construction_type   VARCHAR,
    energy_class        VARCHAR,
    year_built          INTEGER,
    floor               INTEGER,
    has_elevator        BOOLEAN,

    -- Extended scoring fields
    ownership           VARCHAR,            -- 'OV' | 'DV' | 'DV_no_transfer'
    building_revitalized BOOLEAN,
    service_charge      FLOAT,              -- fond oprav CZK/month
    svl_risk            VARCHAR,            -- 'none' | 'proximity' | 'direct'
    locality_tier       INTEGER,            -- 1 (best) | 2 | 3
    city_stigma         BOOLEAN,
    kraj                VARCHAR,            -- Czech region, computed from city/district at insert

    -- Scores (0–100)
    score_total         FLOAT,
    score_yield         FLOAT,
    score_demographic   FLOAT,
    score_economic      FLOAT,
    score_quality       FLOAT,
    score_liquidity     FLOAT,

    estimated_rent      FLOAT,              -- CZK/month
    gross_yield_pct     FLOAT,

    raw_data            JSONB,
    created_at          TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_properties_id             ON properties (id);
CREATE INDEX IF NOT EXISTS ix_properties_price          ON properties (price);
CREATE INDEX IF NOT EXISTS ix_properties_locality_tier  ON properties (locality_tier);
CREATE INDEX IF NOT EXISTS ix_properties_kraj           ON properties (kraj);
CREATE INDEX IF NOT EXISTS ix_properties_score_total    ON properties (score_total);
CREATE INDEX IF NOT EXISTS ix_properties_gross_yield_pct ON properties (gross_yield_pct);
CREATE INDEX IF NOT EXISTS ix_properties_created_at     ON properties (created_at);

-- ---------------------------------------------------------------------------
-- Table: price_benchmarks
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS price_benchmarks (
    id              SERIAL PRIMARY KEY,
    city            VARCHAR NOT NULL,       -- normalized from district (e.g. 'Brno', 'Praha 4')
    disposition     VARCHAR,                -- '2+1', '3+kk', etc.; NULL = all types combined
    avg_price_m2    FLOAT NOT NULL,
    median_price_m2 FLOAT NOT NULL,
    sample_size     INTEGER NOT NULL,
    updated_at      TIMESTAMP DEFAULT NOW(),
    CONSTRAINT uq_price_benchmarks_city_disposition UNIQUE (city, disposition)
);

CREATE INDEX IF NOT EXISTS ix_price_benchmarks_id ON price_benchmarks (id);

-- ---------------------------------------------------------------------------
-- Table: rent_benchmarks
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS rent_benchmarks (
    id               SERIAL PRIMARY KEY,
    city             VARCHAR NOT NULL,
    disposition      VARCHAR NOT NULL,
    median_rent      INTEGER,
    listing_count    INTEGER,
    updated_at       TIMESTAMP DEFAULT NOW(),
    UNIQUE (city, disposition)
);

CREATE INDEX IF NOT EXISTS ix_rent_benchmarks_id ON rent_benchmarks (id);
