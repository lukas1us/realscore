"""
Unit testy pro backend/services/scoring.py

Testují pouze pure funkce bez HTTP a DB závislostí.
compute_scores() se netestuje přímo — závisí na scrape_rental_estimates() (HTTP).
"""

import pytest
from backend.services.scoring import (
    score_locality_svl,
    score_penb,
    score_ownership,
    score_physical,
    _yield_to_score,
    collateral_coefficient,
    monthly_mortgage_payment,
    compute_financial,
    _build_red_flags,
    _build_summary,
)


# ---------------------------------------------------------------------------
# score_locality_svl
# ---------------------------------------------------------------------------

class TestScoreLocalitySvl:
    def test_tier1_no_risk(self):
        assert score_locality_svl("none", 1, False) == 90.0

    def test_tier2_no_risk(self):
        assert score_locality_svl("none", 2, False) == 60.0

    def test_tier3_no_risk(self):
        assert score_locality_svl("none", 3, False) == 25.0

    def test_unknown_tier_defaults_to_60(self):
        assert score_locality_svl("none", None, False) == 60.0

    def test_svl_direct_penalty(self):
        # Tier 1 (90) − 50 = 40
        assert score_locality_svl("direct", 1, False) == 40.0

    def test_svl_proximity_penalty(self):
        # Tier 1 (90) − 20 = 70
        assert score_locality_svl("proximity", 1, False) == 70.0

    def test_city_stigma_penalty(self):
        # Tier 1 (90) − 10 = 80
        assert score_locality_svl("none", 1, True) == 80.0

    def test_all_penalties_combined(self):
        # Tier 3 (25) − 50 (direct) − 10 (stigma) = −35 → clamp to 0
        assert score_locality_svl("direct", 3, True) == 0.0

    def test_svl_direct_tier2(self):
        # Tier 2 (60) − 50 = 10
        assert score_locality_svl("direct", 2, False) == 10.0

    def test_no_svl_risk_none_string(self):
        assert score_locality_svl(None, 2, None) == 60.0


# ---------------------------------------------------------------------------
# score_penb
# ---------------------------------------------------------------------------

class TestScorePenb:
    @pytest.mark.parametrize("cls,expected", [
        ("A", 100.0),
        ("B", 85.0),
        ("C", 70.0),
        ("D", 50.0),
        ("E", 30.0),
        ("F", 10.0),
        ("G", 0.0),
    ])
    def test_known_classes(self, cls, expected):
        assert score_penb(cls) == expected

    def test_lowercase_input(self):
        assert score_penb("a") == 100.0
        assert score_penb("g") == 0.0

    def test_unknown_class_returns_neutral(self):
        assert score_penb("X") == 50.0

    def test_none_returns_neutral(self):
        assert score_penb(None) == 50.0

    def test_empty_string_returns_neutral(self):
        assert score_penb("") == 50.0


# ---------------------------------------------------------------------------
# score_ownership
# ---------------------------------------------------------------------------

class TestScoreOwnership:
    def test_ov(self):
        assert score_ownership("OV") == 100.0

    def test_dv(self):
        assert score_ownership("DV") == 40.0

    def test_dv_no_transfer(self):
        assert score_ownership("DV_no_transfer") == 10.0

    def test_unknown_returns_60(self):
        assert score_ownership(None) == 60.0
        assert score_ownership("") == 60.0
        assert score_ownership("other") == 60.0


# ---------------------------------------------------------------------------
# score_physical
# ---------------------------------------------------------------------------

class TestScorePhysical:
    def test_cihla_ideal_floor_revitalized(self):
        # cihla=100, floor 3=90+10(elevator)=100, revit=100
        # 0.4*100 + 0.35*100 + 0.25*100 = 100
        score = score_physical("cihla", 3, True, True)
        assert score == 100.0

    def test_panel_no_elevator_no_revit(self):
        # panel=30, floor 4 bez výtahu = 90-25=65, revit=30
        # 0.4*30 + 0.35*65 + 0.25*30 = 12 + 22.75 + 7.5 = 42.25
        score = score_physical("panel", 4, False, False)
        assert score == pytest.approx(42.25, abs=0.1)

    def test_unknown_construction_defaults_to_50(self):
        score = score_physical(None, 3, None, None)
        # c=50, f=90 (floor 3), r=60 → 0.4*50 + 0.35*90 + 0.25*60 = 20+31.5+15 = 66.5
        assert score == pytest.approx(66.5, abs=0.1)

    def test_ground_floor_score(self):
        # Přízemí (floor=0): f_score=60
        score = score_physical("cihla", 0, None, None)
        # c=100, f=60, r=60 → 0.4*100 + 0.35*60 + 0.25*60 = 40+21+15 = 76
        assert score == pytest.approx(76.0, abs=0.1)

    def test_high_floor_without_elevator(self):
        # floor=6 (70), bez výtahu → 70-25=45
        score = score_physical("cihla", 6, False, None)
        # c=100, f=45, r=60 → 40+15.75+15 = 70.75
        assert score == pytest.approx(70.75, abs=0.1)

    def test_elevator_bonus_capped_at_100(self):
        # floor 3: 90+10=100 (max), elevator bonus
        score = score_physical("cihla", 3, True, True)
        assert score == 100.0

    def test_score_never_below_zero(self):
        # Extrémní případ: panel, přízemí, bez výtahu, nerevitalizovaný
        score = score_physical("panel", 0, False, False)
        assert score >= 0.0

    def test_score_never_above_100(self):
        score = score_physical("cihla", 3, True, True)
        assert score <= 100.0


# ---------------------------------------------------------------------------
# _yield_to_score
# ---------------------------------------------------------------------------

class TestYieldToScore:
    def test_above_8_pct(self):
        assert _yield_to_score(8.0) == 100.0
        assert _yield_to_score(10.0) == 100.0

    def test_6_pct(self):
        assert _yield_to_score(6.0) == 60.0

    def test_between_6_and_8(self):
        # yield=7 → 60 + (7-6)/2 * 40 = 60+20 = 80
        assert _yield_to_score(7.0) == pytest.approx(80.0)

    def test_4_pct(self):
        assert _yield_to_score(4.0) == 30.0

    def test_between_4_and_6(self):
        # yield=5 → 30 + (5-4)/2 * 30 = 30+15 = 45
        assert _yield_to_score(5.0) == pytest.approx(45.0)

    def test_2_pct(self):
        assert _yield_to_score(2.0) == 0.0

    def test_between_2_and_4(self):
        # yield=3 → (3-2)/2 * 30 = 15
        assert _yield_to_score(3.0) == pytest.approx(15.0)

    def test_below_2_pct(self):
        assert _yield_to_score(0.0) == 0.0
        assert _yield_to_score(1.0) == 0.0


# ---------------------------------------------------------------------------
# collateral_coefficient
# ---------------------------------------------------------------------------

class TestCollateralCoefficient:
    def test_tier1_no_risk(self):
        assert collateral_coefficient(1, "none", False) == 0.95

    def test_tier2_no_risk(self):
        assert collateral_coefficient(2, "none", False) == 0.85

    def test_tier3_no_risk(self):
        assert collateral_coefficient(3, "none", False) == 0.75

    def test_unknown_tier_defaults_to_tier2(self):
        assert collateral_coefficient(None, "none", False) == 0.85

    def test_svl_direct_caps_at_058(self):
        # Tier 1 (0.95) → capped at 0.58
        assert collateral_coefficient(1, "direct", False) == 0.58

    def test_svl_proximity_caps_at_077(self):
        # Tier 1 (0.95) → capped at 0.77
        assert collateral_coefficient(1, "proximity", False) == 0.77

    def test_city_stigma_subtracts_005(self):
        assert collateral_coefficient(2, "none", True) == pytest.approx(0.80)

    def test_minimum_clamp_050(self):
        # Tier 3 (0.75), direct (cap 0.58), stigma (-0.05) = 0.53 → but direct caps at 0.58, then -0.05 = 0.53
        result = collateral_coefficient(3, "direct", True)
        assert result >= 0.50

    def test_maximum_clamp_098(self):
        result = collateral_coefficient(1, "none", False)
        assert result <= 0.98


# ---------------------------------------------------------------------------
# monthly_mortgage_payment
# ---------------------------------------------------------------------------

class TestMonthlyMortgagePayment:
    def test_standard_values(self):
        # 3 mil, 5 %, 30 let
        payment = monthly_mortgage_payment(3_000_000, 5.0, 30)
        # Přibližně 16 105 Kč
        assert 15_000 < payment < 17_000

    def test_zero_interest_rate(self):
        # Splátka = principal / (years*12)
        payment = monthly_mortgage_payment(1_200_000, 0.0, 10)
        assert payment == pytest.approx(10_000.0, rel=1e-6)

    def test_higher_rate_means_higher_payment(self):
        p1 = monthly_mortgage_payment(2_000_000, 3.0, 30)
        p2 = monthly_mortgage_payment(2_000_000, 6.0, 30)
        assert p2 > p1

    def test_shorter_term_means_higher_payment(self):
        p1 = monthly_mortgage_payment(2_000_000, 5.0, 30)
        p2 = monthly_mortgage_payment(2_000_000, 5.0, 15)
        assert p2 > p1


# ---------------------------------------------------------------------------
# compute_financial
# ---------------------------------------------------------------------------

class TestComputeFinancial:
    def test_no_price_returns_nulls(self):
        result = compute_financial(None, None, None, None, None, None, None)
        assert result["collateral_value"] is None
        assert result["max_mortgage"] is None

    def test_collateral_and_mortgage_computed(self):
        result = compute_financial(
            price=4_000_000, estimated_rent=None, service_charge=None,
            locality_tier=1, svl_risk="none", city_stigma=False, gross_yield_pct=None,
        )
        # koef=0.95 → collateral=3_800_000, mortgage=3_040_000
        assert result["collateral_value"] == 3_800_000
        assert result["max_mortgage"] == 3_040_000
        assert result["net_yield_pct"] is None

    def test_with_rent_computes_yield_and_cashflow(self):
        result = compute_financial(
            price=3_000_000, estimated_rent=15_000, service_charge=None,
            locality_tier=2, svl_risk="none", city_stigma=False, gross_yield_pct=None,
        )
        # čistý nájem = 15_000 * 0.72 = 10_800
        # net_yield = 10_800 * 12 / 3_000_000 * 100 = 4.32 %
        assert result["net_yield_pct"] == pytest.approx(4.32, abs=0.01)
        assert result["monthly_cashflow"] is not None

    def test_service_charge_reduces_net_rent(self):
        r1 = compute_financial(3_000_000, 15_000, None, 2, "none", False, None)
        r2 = compute_financial(3_000_000, 15_000, 2_000, 2, "none", False, None)
        assert r2["net_yield_pct"] < r1["net_yield_pct"]


# ---------------------------------------------------------------------------
# _build_red_flags
# ---------------------------------------------------------------------------

class TestBuildRedFlags:
    def _scores(self, **overrides):
        base = {
            "score_demographic": 70,
            "score_economic": 70,
            "score_liquidity": 70,
            "score_quality": 70,
            "score_yield": 70,
            "score_total": 70,
            "city_stigma": False,
        }
        base.update(overrides)
        return base

    def test_no_flags_for_good_property(self):
        flags = _build_red_flags(self._scores(), {"ownership": "OV", "svl_risk": "none"})
        assert flags == []

    def test_low_score_generates_flag(self):
        flags = _build_red_flags(self._scores(score_demographic=30), {})
        assert any("lokalita" in f for f in flags)

    def test_dv_no_transfer_flag(self):
        flags = _build_red_flags(self._scores(), {"ownership": "DV_no_transfer"})
        assert any("BEZ možnosti převodu" in f for f in flags)

    def test_dv_flag(self):
        flags = _build_red_flags(self._scores(), {"ownership": "DV"})
        assert any("Družstevní vlastnictví" in f for f in flags)

    def test_svl_direct_flag(self):
        flags = _build_red_flags(self._scores(), {"svl_risk": "direct"})
        assert any("přímá sociálně vyloučená" in f for f in flags)

    def test_svl_proximity_flag(self):
        flags = _build_red_flags(self._scores(), {"svl_risk": "proximity"})
        assert any("blízkost" in f for f in flags)

    def test_city_stigma_flag(self):
        flags = _build_red_flags(self._scores(), {"city_stigma": True})
        assert any("stigmatizace" in f for f in flags)

    def test_energy_class_fg_flag(self):
        flags = _build_red_flags(self._scores(), {"energy_class": "F"})
        assert any("PENB" in f for f in flags)

    def test_high_price_per_m2_flag(self):
        prop = {"price": 10_000_000, "size_m2": 50}  # 200k/m²
        flags = _build_red_flags(self._scores(), prop)
        assert any("cena za m²" in f for f in flags)

    def test_multiple_flags(self):
        scores = self._scores(score_demographic=20, score_economic=15)
        flags = _build_red_flags(scores, {"svl_risk": "direct", "ownership": "DV"})
        assert len(flags) >= 3


# ---------------------------------------------------------------------------
# _build_summary
# ---------------------------------------------------------------------------

class TestBuildSummary:
    def _scores(self, total=70, gross_yield=None):
        return {
            "score_total": total,
            "gross_yield_pct": gross_yield,
            "city_stigma": False,
        }

    def test_high_score_label(self):
        summary = _build_summary(self._scores(total=75), {"city": "Brno"})
        assert "nadprůměrnou" in summary

    def test_medium_score_label(self):
        summary = _build_summary(self._scores(total=55), {"city": "Brno"})
        assert "průměrnou" in summary

    def test_low_score_label(self):
        summary = _build_summary(self._scores(total=35), {"city": "Brno"})
        assert "výraznými riziky" in summary

    def test_contains_city_name(self):
        summary = _build_summary(self._scores(), {"city": "Ostrava"})
        assert "Ostrava" in summary

    def test_contains_disposition(self):
        summary = _build_summary(self._scores(), {"city": "Brno", "disposition": "3+1"})
        assert "3+1" in summary

    def test_high_yield_mentioned(self):
        summary = _build_summary(self._scores(gross_yield=7.0), {"city": "Brno"})
        assert "atraktivní" in summary

    def test_low_yield_mentioned(self):
        summary = _build_summary(self._scores(gross_yield=2.5), {"city": "Brno"})
        assert "pod průměrem" in summary

    def test_tier1_locality_mentioned(self):
        prop = {"city": "Brno", "locality_tier": 1}
        summary = _build_summary(self._scores(), prop)
        assert "zástavní hodnot" in summary

    def test_returns_string(self):
        summary = _build_summary(self._scores(), {"city": "Praha"})
        assert isinstance(summary, str)
        assert len(summary) > 0
