"""
SQL smoke testy — vyžadují běžící PostgreSQL.

Testují:
  - ORM insert + read (Property, PriceBenchmark)
  - _apply_filters() přes přímé ORM dotazy (kraj, price, energy_class, city, yield)
  - get_benchmark() lookup + fallback na city-wide benchmark
  - refresh_benchmarks() — spustí se bez chyby a vrátí > 0 řádků
"""

import pytest
from sqlalchemy import func

from backend.models import Property, PriceBenchmark
from backend.services.benchmarks import get_benchmark, refresh_benchmarks


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_property(**kwargs) -> Property:
    defaults = dict(
        url="https://www.sreality.cz/detail/-/-/-/-/12345",
        address="Testovací 1",
        city="Brno",
        district="Brno",
        price=3_000_000.0,
        size_m2=60.0,
        disposition="2+1",
        construction_type="cihla",
        energy_class="C",
        locality_tier=2,
        kraj="Jihomoravský kraj",
        score_total=65.0,
        score_yield=50.0,
        score_demographic=70.0,
        score_economic=70.0,
        score_quality=60.0,
        score_liquidity=100.0,
        gross_yield_pct=6.0,
        estimated_rent=15_000.0,
    )
    defaults.update(kwargs)
    return Property(**defaults)


def _make_benchmark(city, disposition, avg, median, n) -> PriceBenchmark:
    return PriceBenchmark(
        city=city,
        disposition=disposition,
        avg_price_m2=avg,
        median_price_m2=median,
        sample_size=n,
    )


# ---------------------------------------------------------------------------
# ORM: insert + read
# ---------------------------------------------------------------------------

class TestOrmBasic:
    def test_insert_and_read_property(self, db):
        prop = _make_property()
        db.add(prop)
        db.commit()

        loaded = db.query(Property).filter_by(city="Brno").first()
        assert loaded is not None
        assert loaded.price == 3_000_000.0
        assert loaded.kraj == "Jihomoravský kraj"

    def test_insert_and_read_benchmark(self, db):
        bm = _make_benchmark("Brno", "2+1", 120_000, 115_000, 50)
        db.add(bm)
        db.commit()

        loaded = db.query(PriceBenchmark).filter_by(city="Brno", disposition="2+1").first()
        assert loaded is not None
        assert loaded.avg_price_m2 == 120_000
        assert loaded.sample_size == 50

    def test_benchmark_unique_constraint(self, db):
        db.add(_make_benchmark("Praha", "3+kk", 200_000, 195_000, 30))
        db.commit()

        from sqlalchemy.exc import IntegrityError
        db.add(_make_benchmark("Praha", "3+kk", 210_000, 205_000, 35))
        with pytest.raises(IntegrityError):
            db.commit()


# ---------------------------------------------------------------------------
# _apply_filters() — testováno přes ORM dotazy (stejná logika jako router)
# ---------------------------------------------------------------------------

class TestFilters:
    def _insert_sample_data(self, db):
        db.add_all([
            _make_property(city="Brno", district="Brno", kraj="Jihomoravský kraj",
                           price=3_000_000, energy_class="B", locality_tier=1,
                           gross_yield_pct=6.5),
            _make_property(city="Ostrava", district="Ostrava", kraj="Moravskoslezský kraj",
                           price=1_500_000, energy_class="D", locality_tier=3,
                           gross_yield_pct=8.0),
            _make_property(city="Praha", district="Praha 4", kraj="Hlavní město Praha",
                           price=8_000_000, energy_class="A", locality_tier=1,
                           gross_yield_pct=3.5),
        ])
        db.commit()

    def test_filter_by_kraj(self, db):
        self._insert_sample_data(db)
        results = db.query(Property).filter(Property.kraj.in_(["Jihomoravský kraj"])).all()
        assert len(results) == 1
        assert results[0].city == "Brno"

    def test_filter_price_min(self, db):
        self._insert_sample_data(db)
        results = db.query(Property).filter(Property.price >= 5_000_000).all()
        assert len(results) == 1
        assert results[0].city == "Praha"

    def test_filter_price_max(self, db):
        self._insert_sample_data(db)
        results = db.query(Property).filter(Property.price <= 2_000_000).all()
        assert len(results) == 1
        assert results[0].city == "Ostrava"

    def test_filter_price_range(self, db):
        self._insert_sample_data(db)
        results = (
            db.query(Property)
            .filter(Property.price >= 2_000_000, Property.price <= 5_000_000)
            .all()
        )
        assert len(results) == 1
        assert results[0].city == "Brno"

    def test_filter_energy_class(self, db):
        self._insert_sample_data(db)
        results = db.query(Property).filter(Property.energy_class.in_(["A", "B"])).all()
        assert len(results) == 2
        cities = {r.city for r in results}
        assert cities == {"Brno", "Praha"}

    def test_filter_by_city(self, db):
        self._insert_sample_data(db)
        results = db.query(Property).filter(Property.city.in_(["Ostrava"])).all()
        assert len(results) == 1
        assert results[0].city == "Ostrava"

    def test_filter_min_yield(self, db):
        self._insert_sample_data(db)
        results = db.query(Property).filter(Property.gross_yield_pct >= 6.0).all()
        assert len(results) == 2
        cities = {r.city for r in results}
        assert cities == {"Brno", "Ostrava"}

    def test_multiple_filters_combined(self, db):
        self._insert_sample_data(db)
        results = (
            db.query(Property)
            .filter(
                Property.kraj.in_(["Jihomoravský kraj", "Hlavní město Praha"]),
                Property.price <= 5_000_000,
            )
            .all()
        )
        assert len(results) == 1
        assert results[0].city == "Brno"

    def test_no_results_when_no_match(self, db):
        self._insert_sample_data(db)
        results = db.query(Property).filter(Property.kraj.in_(["Plzeňský kraj"])).all()
        assert results == []

    def test_count_query(self, db):
        self._insert_sample_data(db)
        total = db.query(func.count(Property.id)).scalar()
        assert total == 3


# ---------------------------------------------------------------------------
# get_benchmark() — lookup + fallback
# ---------------------------------------------------------------------------

class TestGetBenchmark:
    def test_exact_match(self, db):
        db.add(_make_benchmark("Brno", "2+1", 120_000, 115_000, 42))
        db.commit()

        result = get_benchmark(db, district="Brno", disposition="2+1")
        assert result is not None
        assert result["city"] == "Brno"
        assert result["disposition"] == "2+1"
        assert result["avg_price_m2"] == 120_000
        assert result["sample_size"] == 42

    def test_fallback_to_city_wide(self, db):
        # Jen city-wide (NULL disposition), žádná per-disposition
        db.add(_make_benchmark("Kyjov", None, 70_000, 68_000, 10))
        db.commit()

        result = get_benchmark(db, district="Kyjov", disposition="3+kk")
        assert result is not None
        assert result["city"] == "Kyjov"
        assert result["disposition"] is None  # fallback vrátil city-wide

    def test_specific_beats_city_wide(self, db):
        db.add_all([
            _make_benchmark("Ostrava", None, 80_000, 78_000, 100),
            _make_benchmark("Ostrava", "2+1", 75_000, 73_000, 25),
        ])
        db.commit()

        result = get_benchmark(db, district="Ostrava", disposition="2+1")
        assert result["disposition"] == "2+1"
        assert result["avg_price_m2"] == 75_000

    def test_normalizes_district_with_suffix(self, db):
        # "Brno - Žebětín" → city="Brno"
        db.add(_make_benchmark("Brno", "2+kk", 125_000, 120_000, 30))
        db.commit()

        result = get_benchmark(db, district="Brno - Žebětín", disposition="2+kk")
        assert result is not None
        assert result["city"] == "Brno"

    def test_unknown_city_returns_none(self, db):
        result = get_benchmark(db, district="Neexistující město", disposition="2+1")
        assert result is None

    def test_none_district_returns_none(self, db):
        result = get_benchmark(db, district=None, disposition="2+1")
        assert result is None


# ---------------------------------------------------------------------------
# refresh_benchmarks()
# ---------------------------------------------------------------------------

class TestRefreshBenchmarks:
    def test_refresh_from_properties(self, db):
        # Vlož dostatek nemovitostí pro alespoň jeden benchmark (min. 3 na skupinu)
        for i in range(5):
            db.add(_make_property(
                url=f"https://www.sreality.cz/detail/{i}",
                district="Brno",
                disposition="2+1",
                price=3_000_000 + i * 100_000,
                size_m2=60.0,
            ))
        db.commit()

        count = refresh_benchmarks(db)
        assert count > 0

        bm = db.query(PriceBenchmark).filter_by(city="Brno", disposition="2+1").first()
        assert bm is not None
        assert bm.avg_price_m2 > 0
        assert bm.sample_size == 5

    def test_refresh_is_idempotent(self, db):
        for i in range(4):
            db.add(_make_property(
                url=f"https://www.sreality.cz/detail/idem/{i}",
                district="Ostrava",
                disposition="3+1",
                price=2_000_000 + i * 50_000,
                size_m2=75.0,
            ))
        db.commit()

        count1 = refresh_benchmarks(db)
        count2 = refresh_benchmarks(db)
        assert count1 == count2

    def test_groups_below_min_sample_excluded(self, db):
        # Pouze 2 záznamy → pod minimem 3, benchmark nevznikne
        for i in range(2):
            db.add(_make_property(
                url=f"https://www.sreality.cz/detail/small/{i}",
                district="MaléMěsto",
                disposition="1+kk",
                price=1_500_000,
                size_m2=30.0,
            ))
        db.commit()

        refresh_benchmarks(db)
        bm = db.query(PriceBenchmark).filter_by(city="MaléMěsto").first()
        assert bm is None
