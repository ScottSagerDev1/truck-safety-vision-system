"""
Data types and tunable constants for the TSV behavioral scoring engine.

Everything numeric that the design doc (docs/scoring-design.md) calls a
decision lives in this file, so recalibrating the system means editing
one place and re-running the tests.
"""

from dataclasses import dataclass, field
from datetime import date
from enum import Enum


# ---------------------------------------------------------------------------
# Enumerations — the closed sets of values an event can carry
# ---------------------------------------------------------------------------

class Ledger(Enum):
    """Which score an event lands on. See design doc section 0."""
    DRIVER = "driver"
    COMPANY = "company"


class EventType(Enum):
    TAILGATING = "tailgating"
    HOS = "hos"


class Source(Enum):
    """Where the event came from. Only affects bookkeeping, not weight."""
    TSV_OBSERVED = "tsv_observed"   # another truck's TSV unit saw it -> company ledger
    ELD = "eld"                     # hours-of-service log -> driver ledger
    ROADSIDE = "roadside"           # inspection citation -> driver ledger
    SELF_REPORT = "self_report"     # driver's own truck (future phase) -> driver ledger


class Band(Enum):
    EXEMPLARY = "Exemplary"
    GOOD = "Good"
    WATCH = "Watch"
    INTERVENTION = "Intervention"
    HIGH_RISK = "High Risk"


# ---------------------------------------------------------------------------
# Tunables — design doc sections 2.2 to 2.4, 3.2, 3.3
# ---------------------------------------------------------------------------

BASE_WEIGHT = {
    EventType.TAILGATING: 60.0,
    EventType.HOS: 40.0,
}

TIER_MULT = {1: 1.0, 2: 1.5, 3: 2.5}

# Trailing window (days) used to count repeats for the frequency multiplier.
FREQ_WINDOW_DAYS = {
    EventType.TAILGATING: 30,
    EventType.HOS: 90,
}
FREQ_STEP = 0.3          # each repeat adds this much to the multiplier
FREQ_CAP = 3.0

# Grace: tailgating only, first event in this many days, tier <= 2 -> half price.
GRACE_LOOKBACK_DAYS = 60
GRACE_FACTOR = 0.5
GRACE_MAX_TIER = 2

HALF_LIFE_DAYS = {
    EventType.TAILGATING: 180,
    EventType.HOS: 90,
}
FORGET_AFTER_DAYS = 730   # 24 months: event no longer contributes at all

# Driver score structure: S = 800 + T - P
DRIVER_START = 800.0
TRUST_CAP = 200.0
TRUST_CLEAN_MONTH = 20.0
TRUST_TIER1_ONLY_MONTH = 10.0
TRUST_LOSS_PER_EVENT = 40.0

SCORE_MIN, SCORE_MAX = 0.0, 1000.0

# Company aggregation
BAD_DRIVER_THRESHOLD = 600.0   # driver counts as "bad" below this
REFERENCE_FLEET_SIZE = 50      # the 50/N normalization anchor
PROGRAM_BONUS_CAP = 50.0
COMPANY_DEFAULT_M = 800.0      # baseline when a company has no drivers on file


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Event:
    """One violation. Immutable once created — the engine annotates it by
    producing a WeightedEvent rather than mutating this."""
    when: date
    type: EventType
    tier: int
    ledger: Ledger
    source: Source

    def __post_init__(self):
        if self.tier not in TIER_MULT:
            raise ValueError(f"tier must be 1, 2, or 3; got {self.tier}")


@dataclass(frozen=True)
class WeightedEvent:
    """An Event plus the factors the engine computed for it at the time it
    happened. These are frozen — decay is applied later, at scoring time,
    but the multipliers never change after the fact."""
    event: Event
    base: float
    tier_mult: float
    freq_mult: float
    grace: float

    @property
    def weight(self) -> float:
        return self.base * self.tier_mult * self.freq_mult * self.grace


@dataclass
class DriverScore:
    score: float
    trust: float
    penalty: float
    band: Band
    weighted_events: list = field(default_factory=list)


@dataclass
class CompanyScore:
    score: float
    baseline_m: float
    bad_driver_penalty_b: float
    tailgating_penalty_pc: float
    program_bonus_g: float
    band: Band
    bad_driver_count: int
    fleet_size: int
