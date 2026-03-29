from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, JSON, Boolean, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB

from backend.database import Base


class Property(Base):
    __tablename__ = "properties"

    id = Column(Integer, primary_key=True, index=True)
    url = Column(String, nullable=True)
    address = Column(String, nullable=True)
    city = Column(String, nullable=True)
    district = Column(String, nullable=True)

    price = Column(Float, nullable=True, index=True)  # CZK
    size_m2 = Column(Float, nullable=True)
    disposition = Column(String, nullable=True)    # e.g. "2+1", "3+kk"
    construction_type = Column(String, nullable=True)  # panel / cihla / ...
    energy_class = Column(String, nullable=True)   # A / B / C / ...
    year_built = Column(Integer, nullable=True)
    floor = Column(Integer, nullable=True)
    has_elevator = Column(Boolean, nullable=True)

    # --- Nová pole pro rozšířený scoring ---
    ownership = Column(String, nullable=True)           # "OV" | "DV" | "DV_no_transfer"
    building_revitalized = Column(Boolean, nullable=True)  # zda byl dům revitalizován
    service_charge = Column(Float, nullable=True)       # fond oprav Kč/měsíc
    svl_risk = Column(String, nullable=True)            # "none" | "proximity" | "direct"
    locality_tier = Column(Integer, nullable=True, index=True)  # 1 (nejlepší) | 2 | 3
    city_stigma = Column(Boolean, nullable=True)        # Most, Chomutov atd. = True
    kraj = Column(String, nullable=True, index=True)    # computed z CITY_TO_REGION při ukládání

    # Scores (0–100)
    # Poznámka: sloupce jsou přemapovány na nové dimenze (scoring model v2):
    #   score_yield       → výnosnost (10 %)
    #   score_demographic → lokalita / SVL čistota (40 %)
    #   score_economic    → PENB / energetická třída (20 %)
    #   score_quality     → fyzické parametry (15 %)
    #   score_liquidity   → vlastnictví OV/DV (15 %)
    score_total = Column(Float, nullable=True, index=True)
    score_yield = Column(Float, nullable=True)
    score_demographic = Column(Float, nullable=True)
    score_economic = Column(Float, nullable=True)
    score_quality = Column(Float, nullable=True)
    score_liquidity = Column(Float, nullable=True)

    estimated_rent = Column(Float, nullable=True)  # CZK/month
    gross_yield_pct = Column(Float, nullable=True, index=True)

    raw_data = Column(JSONB, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


class RentBenchmark(Base):
    __tablename__ = "rent_benchmarks"
    __table_args__ = (UniqueConstraint("city", "disposition", name="uq_rent_benchmarks_city_disposition"),)

    id = Column(Integer, primary_key=True, index=True)
    city = Column(String, nullable=False)
    disposition = Column(String, nullable=False)
    median_rent = Column(Integer, nullable=True)    # CZK/month
    listing_count = Column(Integer, nullable=True)  # number of active rental listings
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PriceBenchmark(Base):
    __tablename__ = "price_benchmarks"
    __table_args__ = (UniqueConstraint("city", "disposition", name="uq_price_benchmarks_city_disposition"),)

    id = Column(Integer, primary_key=True, index=True)
    city = Column(String, nullable=False)           # normalized from district
    disposition = Column(String, nullable=True)     # None = all dispositions combined
    avg_price_m2 = Column(Float, nullable=False)
    median_price_m2 = Column(Float, nullable=False)
    sample_size = Column(Integer, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
