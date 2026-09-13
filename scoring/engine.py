"""
TSV behavioral scoring engine.

Pure functions, no I/O, no database. Give it events and a date, get a score.
Every formula here maps to a numbered section of docs/scoring-design.md.
"""

from datetime import date, timedelta
from math import ceil

from .models import (
    BAD_DRIVER_THRESHOLD, BASE_WEIGHT, Band, COMPANY_DEFAULT_M, CompanyScore,
    DRIVER_START, DriverScore, Event, EventType, FORGET_AFTER_DAYS, FREQ_CAP,
    FREQ_STEP, FREQ_WINDOW_DAYS, GRACE_FACTOR, GRACE_LOOKBACK_DAYS,
    GRACE_MAX_TIER, HALF_LIFE_DAYS, Ledger, PROGRAM_BONUS_CAP,
    REFERENCE_FLEET_SIZE, SCORE_MAX, SCORE_MIN, TIER_MULT, TRUST_CAP,
    TRUST_CLEAN_MONTH, TRUST_LOSS_PER_EVENT, TRUST_TIER1_ONLY_MONTH,
    WeightedEvent,
)


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def clamp(x: float, lo: float = SCORE_MIN, hi: float = SCORE_MAX) -> float:
    return max(lo, min(hi, x))


def band_for(score: float) -> Band:
    """Design doc 2.5."""
    if score >= 900:
        return Band.EXEMPLARY
    if score >= 800:
        return Band.GOOD
    if score >= 700:
        return Band.WATCH
    if score >= 600:
        return Band.INTERVENTION
    return Band.HIGH_RISK


# ---------------------------------------------------------------------------
# Section 2.2 — per-event weight
# ---------------------------------------------------------------------------

def weigh_events(events: list[Event], fleet_size: int = REFERENCE_FLEET_SIZE
                 ) -> list[WeightedEvent]:
    """
    Walk events in time order and compute each one's frozen multipliers.

    The frequency multiplier and grace both depend on what came *before*
    the event, so events must be processed oldest-first. fleet_size only
    matters for the company ledger, where repeat counts are normalized to
    a 50-truck fleet.
    """
    ordered = sorted(events, key=lambda e: e.when)
    out: list[WeightedEvent] = []

    for i, ev in enumerate(ordered):
        earlier = ordered[:i]

        # --- frequency multiplier -------------------------------------
        window = timedelta(days=FREQ_WINDOW_DAYS[ev.type])
        same_type_recent = [
            e for e in earlier
            if e.type == ev.type and e.ledger == ev.ledger
            and ev.when - e.when < window
        ]
        raw_n = len(same_type_recent) + 1          # +1 for this event
        if ev.ledger is Ledger.COMPANY:
            n = ceil(raw_n * REFERENCE_FLEET_SIZE / fleet_size)
        else:
            n = raw_n
        freq_mult = min(1.0 + FREQ_STEP * (n - 1), FREQ_CAP)

        # --- grace: tailgating only ------------------------------------
        grace = 1.0
        if ev.type is EventType.TAILGATING and ev.tier <= GRACE_MAX_TIER:
            lookback = timedelta(days=GRACE_LOOKBACK_DAYS)
            recent_tailgating = any(
                e.type is EventType.TAILGATING and e.ledger == ev.ledger
                and ev.when - e.when < lookback
                for e in earlier
            )
            if not recent_tailgating:
                grace = GRACE_FACTOR

        out.append(WeightedEvent(
            event=ev,
            base=BASE_WEIGHT[ev.type],
            tier_mult=TIER_MULT[ev.tier],
            freq_mult=freq_mult,
            grace=grace,
        ))
    return out


# ---------------------------------------------------------------------------
# Section 2.3 — decay
# ---------------------------------------------------------------------------

def decayed_weight(we: WeightedEvent, as_of: date) -> float:
    age = (as_of - we.event.when).days
    if age < 0 or age >= FORGET_AFTER_DAYS:
        return 0.0
    half_life = HALF_LIFE_DAYS[we.event.type]
    return we.weight * (0.5 ** (age / half_life))


def penalty_mass(weighted: list[WeightedEvent], as_of: date) -> float:
    return sum(decayed_weight(we, as_of) for we in weighted)


# ---------------------------------------------------------------------------
# Section 2.4 — trust credit (driver only)
# ---------------------------------------------------------------------------

def _month_starts(start: date, end: date):
    """Yield the first day of each calendar month from start's month up to
    (but not including) end's month. Used to walk completed months."""
    y, m = start.year, start.month
    while (y, m) < (end.year, end.month):
        yield date(y, m, 1)
        if m == 12:
            y, m = y + 1, 1
        else:
            m += 1


def trust_credit(events: list[Event], employment_start: date, as_of: date
                 ) -> float:
    """
    Replay the driver's history month by month.

    Credit is awarded for each *completed* calendar month of active
    employment; deductions land the day an event occurs. The current
    (incomplete) month earns nothing yet but its events still deduct.
    """
    driver_events = sorted(
        (e for e in events if e.ledger is Ledger.DRIVER and e.when <= as_of),
        key=lambda e: e.when,
    )
    t = 0.0

    for month_start in _month_starts(employment_start, as_of):
        if month_start.month == 12:
            next_month = date(month_start.year + 1, 1, 1)
        else:
            next_month = date(month_start.year, month_start.month + 1, 1)

        in_month = [e for e in driver_events if month_start <= e.when < next_month]

        # deductions first (they happened during the month)
        t = max(0.0, t - TRUST_LOSS_PER_EVENT * len(in_month))

        # then the month's credit
        if not in_month:
            t += TRUST_CLEAN_MONTH
        elif all(e.tier == 1 for e in in_month) and _no_repeats(in_month):
            t += TRUST_TIER1_ONLY_MONTH
        t = min(t, TRUST_CAP)

    # current, incomplete month: deductions only
    current_month_start = date(as_of.year, as_of.month, 1)
    current = [e for e in driver_events if e.when >= current_month_start]
    t = max(0.0, t - TRUST_LOSS_PER_EVENT * len(current))
    return t


def _no_repeats(events_in_month: list[Event]) -> bool:
    seen = set()
    for e in events_in_month:
        if e.type in seen:
            return False
        seen.add(e.type)
    return True


# ---------------------------------------------------------------------------
# Section 2.1 — driver score
# ---------------------------------------------------------------------------

def score_driver(events: list[Event], employment_start: date, as_of: date
                 ) -> DriverScore:
    """S_driver = clamp(800 + T - P_d)."""
    driver_events = [e for e in events if e.ledger is Ledger.DRIVER]
    weighted = weigh_events(driver_events)
    p = penalty_mass(weighted, as_of)
    t = trust_credit(driver_events, employment_start, as_of)
    s = clamp(DRIVER_START + t - p)
    return DriverScore(score=s, trust=t, penalty=p, band=band_for(s),
                       weighted_events=weighted)


# ---------------------------------------------------------------------------
# Section 3 — company score
# ---------------------------------------------------------------------------

def bad_driver_penalty(bad_count: int, fleet_size: int) -> float:
    """3.2: B = k(k+1)/2 * 50/N."""
    if fleet_size <= 0:
        return 0.0
    return (bad_count * (bad_count + 1) / 2) * (REFERENCE_FLEET_SIZE / fleet_size)


def company_tailgating_penalty(company_events: list[Event], fleet_size: int,
                               as_of: date) -> float:
    """3.4: P_c = (sum of decayed weights) * 50/N."""
    if fleet_size <= 0:
        return 0.0
    weighted = weigh_events(company_events, fleet_size=fleet_size)
    return penalty_mass(weighted, as_of) * (REFERENCE_FLEET_SIZE / fleet_size)


def score_company(driver_scores: list[float], company_events: list[Event],
                  fleet_size: int, as_of: date,
                  program_bonus: float = 0.0) -> CompanyScore:
    """S_company = clamp(M - B - P_c + G)."""
    if driver_scores:
        m = sum(driver_scores) / len(driver_scores)
    else:
        m = COMPANY_DEFAULT_M

    k = sum(1 for s in driver_scores if s < BAD_DRIVER_THRESHOLD)
    b = bad_driver_penalty(k, fleet_size)

    obs = [e for e in company_events if e.ledger is Ledger.COMPANY]
    pc = company_tailgating_penalty(obs, fleet_size, as_of)

    g = clamp(program_bonus, 0.0, PROGRAM_BONUS_CAP)

    s = clamp(m - b - pc + g)
    return CompanyScore(score=s, baseline_m=m, bad_driver_penalty_b=b,
                        tailgating_penalty_pc=pc, program_bonus_g=g,
                        band=band_for(s), bad_driver_count=k,
                        fleet_size=fleet_size)
