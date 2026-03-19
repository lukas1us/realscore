-- Migration 001: přidání nových polí pro rozšířený scoring model
-- Spusť na existující databázi jednou: psql -U postgres -d realscoreCZ -f 001_new_fields.sql

ALTER TABLE properties ADD COLUMN IF NOT EXISTS ownership VARCHAR;           -- "OV" | "DV" | "DV_no_transfer"
ALTER TABLE properties ADD COLUMN IF NOT EXISTS building_revitalized BOOLEAN; -- zda byl dům revitalizován
ALTER TABLE properties ADD COLUMN IF NOT EXISTS service_charge FLOAT;         -- fond oprav Kč/měsíc
ALTER TABLE properties ADD COLUMN IF NOT EXISTS svl_risk VARCHAR;             -- "none" | "proximity" | "direct"
ALTER TABLE properties ADD COLUMN IF NOT EXISTS locality_tier INTEGER;        -- 1 (nejlepší) | 2 | 3 (problematická)
ALTER TABLE properties ADD COLUMN IF NOT EXISTS city_stigma BOOLEAN;          -- Most, Chomutov atd. = true

-- Index pro filtrování dle locality_tier
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_properties_locality_tier
    ON properties (locality_tier);
