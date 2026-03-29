-- Migration 004: Create rent_benchmarks table
-- Run this on EXISTING installations (fresh installs use 000_initialization.sql).
--
-- Usage:
--   psql $DATABASE_URL -f backend/database/004_rent_benchmarks.sql

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
