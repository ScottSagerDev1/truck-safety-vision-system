"""
Each test here is a row from a table in docs/scoring-design.md.
If a test fails, either the code or the doc is wrong — find out which.

Run with:  python -m pytest tests/ -v
"""

from datetime import date, timedelta

import pytest

from scoring.engine import (
    bad_driver_penalty, score_company, score_driver, weigh_events,
)
from scoring.models import Band, Event, EventType, Ledger, Source

# A driver who started a year ago with no events has full trust (T = 200)
# and no penalty, so their score is 1000. Every example starts there.
START = date(2025, 9, 1)
TODAY = date(2026, 9, 13)


def hos(when: date, tier: int = 2) -> Event:
    return Event(when, EventType.HOS, tier, Ledger.DRIVER, Source.ELD)


def tail_self(when: date, tier: int = 2) -> Event:
    """Future-phase self-reported tailgating on the driver ledger."""
    return Event(when, EventType.TAILGATING, tier, Ledger.DRIVER, Source.SELF_REPORT)


def tail_obs(when: date, tier: int = 2) -> Event:
    """TSV-observed tailgating on the company ledger."""
    return Event(when, EventType.TAILGATING, tier, Ledger.COMPANY, Source.TSV_OBSERVED)


# ---------------------------------------------------------------------------
# Baseline
# ---------------------------------------------------------------------------

def test_clean_driver_reaches_1000():
    r = score_driver([], START, TODAY)
    assert r.trust == 200
    assert r.penalty == 0
    assert r.score == 1000
    assert r.band is Band.EXEMPLARY


def test_new_driver_starts_at_800():
    r = score_driver([], TODAY, TODAY)
    assert r.score == 800
    assert r.band is Band.GOOD


def test_trust_builds_20_per_clean_month():
    # 5 completed months (Apr..Aug) -> T = 100
    r = score_driver([], date(2026, 4, 1), date(2026, 9, 13))
    assert r.trust == 100
    assert r.score == 900


# ---------------------------------------------------------------------------
# Section 2.7 — HOS on the driver ledger
# Tier 2 = 60 pts, no grace, 90-day window. Events on the scoring day so
# intra-quarter decay doesn't muddy the arithmetic.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("n, expected_score, expected_band", [
    (1, 900, Band.EXEMPLARY),      # 800 + 160 - 60   (900 is the band boundary)
    (2, 782, Band.WATCH),          # 800 + 120 - 138
    (3, 646, Band.INTERVENTION),   # 800 +  80 - 234
    (4, 492, Band.HIGH_RISK),      # 800 +  40 - 348
])
def test_hos_tier2_per_quarter(n, expected_score, expected_band):
    events = [hos(TODAY, tier=2) for _ in range(n)]
    r = score_driver(events, START, TODAY)
    assert r.score == pytest.approx(expected_score)
    assert r.band is expected_band


@pytest.mark.parametrize("n, expected_score", [
    (1, 920), (2, 828), (3, 724), (4, 608),
])
def test_hos_tier1_per_quarter(n, expected_score):
    events = [hos(TODAY, tier=1) for _ in range(n)]
    r = score_driver(events, START, TODAY)
    assert r.score == pytest.approx(expected_score)


@pytest.mark.parametrize("n, expected_score", [
    (1, 860), (2, 690),
])
def test_hos_tier3_per_quarter(n, expected_score):
    events = [hos(TODAY, tier=3) for _ in range(n)]
    r = score_driver(events, START, TODAY)
    assert r.score == pytest.approx(expected_score)


def test_hos_never_gets_grace():
    w = weigh_events([hos(TODAY, tier=2)])
    assert w[0].grace == 1.0


def test_hos_repeat_within_90_days_counts_as_repeat():
    # 60 days apart is still "twice this quarter"
    w = weigh_events([hos(TODAY - timedelta(days=60)), hos(TODAY)])
    assert w[1].freq_mult == pytest.approx(1.3)


def test_hos_repeat_after_90_days_does_not():
    w = weigh_events([hos(TODAY - timedelta(days=91)), hos(TODAY)])
    assert w[1].freq_mult == pytest.approx(1.0)


def test_one_hos_per_quarter_steady_state_stays_below_exemplary():
    """Doc: 'converges to swinging between ~840 and ~940'."""
    events = [hos(TODAY - timedelta(days=90 * q)) for q in range(8)]
    just_after = score_driver(events, START - timedelta(days=730), TODAY)
    assert 820 <= just_after.score <= 860

    end_of_quarter = score_driver(events, START - timedelta(days=730),
                                  TODAY + timedelta(days=89))
    assert 920 <= end_of_quarter.score <= 960
    assert end_of_quarter.score < 1000


# ---------------------------------------------------------------------------
# Section 2.6 — tailgating, tier 2 = 90 pts
# ---------------------------------------------------------------------------

def test_tailgating_one_incident_graced():
    r = score_driver([tail_self(TODAY)], START, TODAY)
    we = r.weighted_events[0]
    assert we.grace == 0.5
    assert we.weight == pytest.approx(45)
    assert r.score == pytest.approx(915)


def test_tailgating_five_in_a_month():
    """w1 = 45 (grace), w2..5 = 90 * (1.3+1.6+1.9+2.2) = 630, P = 675, T = 0."""
    events = [tail_self(TODAY) for _ in range(5)]
    r = score_driver(events, START, TODAY)
    assert r.penalty == pytest.approx(675)
    assert r.trust == 0
    assert r.score == pytest.approx(125)
    assert r.band is Band.HIGH_RISK


def test_tailgating_tier3_never_graced():
    w = weigh_events([tail_self(TODAY, tier=3)])
    assert w[0].grace == 1.0


def test_tailgating_recovery_curve():
    """Doc: crosses 700 around month 9, 900 around month 17."""
    events = [tail_self(TODAY) for _ in range(5)]
    start = START

    def score_at(months):
        return score_driver(events, start, TODAY + timedelta(days=30 * months)).score

    assert score_at(8) < 700 <= score_at(10)
    assert score_at(16) < 900 <= score_at(18)


def test_isolated_tailgating_events_land_in_watch():
    """Five graced hits spread over 70-day gaps. The frequency multiplier
    never fires (all 1.0) but trust can't out-rebuild an event every two
    months (-40 per event vs +20 per clean month), so this lands in Watch,
    not high 800s. Compare test_tailgating_five_in_a_month -> 125."""
    events = [tail_self(TODAY - timedelta(days=70 * i)) for i in range(5)]
    r = score_driver(events, START - timedelta(days=365), TODAY)
    assert all(we.freq_mult == 1.0 for we in r.weighted_events)
    assert 740 <= r.score < 800
    assert r.band is Band.WATCH


def test_events_forgotten_after_24_months():
    r = score_driver([tail_self(TODAY - timedelta(days=731))],
                     START - timedelta(days=1000), TODAY)
    assert r.penalty == 0


# ---------------------------------------------------------------------------
# Section 3.2 — bad-driver penalty, 50-truck fleet: 1, 3, 6, 15, 55
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("k, expected", [(0, 0), (1, 1), (2, 3), (3, 6), (5, 15), (10, 55)])
def test_bad_driver_penalty_curve(k, expected):
    assert bad_driver_penalty(k, 50) == pytest.approx(expected)


def test_bad_driver_penalty_scales_with_fleet_size():
    assert bad_driver_penalty(1, 5) == pytest.approx(10)
    assert bad_driver_penalty(1, 500) == pytest.approx(0.1)


# ---------------------------------------------------------------------------
# Section 3.4 — company tailgating ledger
# ---------------------------------------------------------------------------

def test_company_one_observed_event_50_trucks():
    drivers = [900.0] * 50
    r = score_company(drivers, [tail_obs(TODAY)], fleet_size=50, as_of=TODAY)
    assert r.tailgating_penalty_pc == pytest.approx(45)
    assert r.score == pytest.approx(855)


def test_company_five_observed_events_50_trucks():
    drivers = [900.0] * 50
    events = [tail_obs(TODAY) for _ in range(5)]
    r = score_company(drivers, events, fleet_size=50, as_of=TODAY)
    assert r.tailgating_penalty_pc == pytest.approx(675)
    assert r.band is Band.HIGH_RISK


def test_company_five_events_500_trucks():
    """Fleet-size normalization applies twice: repeat count n is scaled to
    a 50-truck fleet (5 * 50/500 -> ceil(0.5) = 1, so no frequency
    escalation), and the sum is scaled by 50/N. 45 + 4*90 = 405, * 0.1."""
    drivers = [900.0] * 500
    events = [tail_obs(TODAY) for _ in range(5)]
    r = score_company(drivers, events, fleet_size=500, as_of=TODAY)
    assert r.tailgating_penalty_pc == pytest.approx(40.5)


def test_company_five_events_5_trucks_floors_at_zero():
    drivers = [900.0] * 5
    events = [tail_obs(TODAY) for _ in range(5)]
    r = score_company(drivers, events, fleet_size=5, as_of=TODAY)
    assert r.score == 0


def test_company_with_no_drivers_uses_800_baseline():
    r = score_company([], [], fleet_size=1, as_of=TODAY)
    assert r.baseline_m == 800
    assert r.score == 800


def test_program_bonus_capped_at_50():
    r = score_company([850.0] * 50, [], fleet_size=50, as_of=TODAY, program_bonus=80)
    assert r.program_bonus_g == 50
    assert r.score == 900


def test_bad_drivers_hit_both_mean_and_penalty():
    drivers = [900.0] * 47 + [500.0] * 3
    r = score_company(drivers, [], fleet_size=50, as_of=TODAY)
    assert r.bad_driver_count == 3
    assert r.bad_driver_penalty_b == pytest.approx(6)
    assert r.baseline_m == pytest.approx(876)
    assert r.score == pytest.approx(870)
