# TSV Behavioral Scoring System — Algorithm Design v0.2

*All worked-example figures in this document are verified by `tests/test_scoring.py`.*

Design goals: risk-proportional, frequency-based, recoverable, and non-linear at the company level. Higher score = safer. Both driver and company scales run 0–1000.

## 0. Observation model (read this first)

**TSV is a third-party observer, not a self-monitor.** The TSV-equipped truck watches *other* vehicles — typically the adjacent lane — and records tailgating it sees them commit. Its value is coverage of the fleet that has no sensors: older trucks, small carriers, owner-operators. The TSV host is never the scored party.

**Who gets scored by what:**

| Event source | Scored against | Why |
|---|---|---|
| Tailgating observed by TSV | **Company** | TSV identifies the vehicle (plate / USDOT), not the driver. The company knows exactly who was in that truck at that time and is expected to deal with it. No attribution step, no excuse. |
| HOS violation (ELD / roadside) | **Driver** | Already tied to a CDL at the source. |
| Tailgating self-reported by the driver's own truck | **Driver** | *Future phase only.* If TSV were ever adopted, an equipped truck could report its own driver's headway. Not part of the POC. |

Consequences that shape everything below:

- **Two penalty pools, same math.** Driver penalty mass P_d is built from HOS events (and future self-reported tailgating). Company penalty mass P_c is built from observed tailgating events. Both use the same per-event weighting, frequency multiplier, grace, and decay — the difference is which ledger they land in.
- **The company score has two ways to fall:** its drivers' HOS-driven scores dragging the mean down, and its trucks being caught tailgating. A carrier with clean logs and aggressive drivers still gets hit.
- **Coverage is sparse and unbiased.** Any given tailgating truck is caught only when a TSV unit happens to be alongside. Event counts are a *sample* of behavior — a fleet whose trucks tailgate habitually will be caught repeatedly across many observers — which argues for the long half-life and the frequency multiplier rather than heavy per-event penalties.
- **Host-vehicle OEM following-distance sensors are out of scope.** Most new trucks already measure headway, but those alerts go to the carrier's safety department and are rarely acted upon. Feeding them in is a possible later phase; it is not part of the POC.
- **Out of scope for POC:** fatigue detection, cross-fleet fairness normalization.

---

## 1. FMCSA CSA research summary

CSA's Safety Measurement System scores **carriers, not drivers**. Roadside inspection violations and crashes are grouped into compliance categories (formerly "BASICs"): Unsafe Driving, HOS Compliance, Crash Indicator, Vehicle Maintenance, Controlled Substances/Alcohol, Hazmat, and Driver Fitness. A carrier's measure in each category is ranked as a **percentile against a peer group of similar size/exposure**; a high percentile (worse) above an intervention threshold triggers warning letters, investigations, and ultimately authority action.

Key structural facts relevant to TSV:

- **Severity.** The original 1–10 severity scale was replaced in the 2025–2026 overhaul with a two-value scale: weight 2 for out-of-service or driver-disqualifying violations, weight 1 for everything else. FMCSA concluded that noting *that* a violation occurred mattered more than fine-grained weighting. Following-too-close sits in Unsafe Driving (historically severity 5 of 10; now weight 1 unless disqualifying).
- **Time weighting.** A 24-month window with recency emphasis — recent 6 months count most, then reduced weight, then dropped at 24 months. The overhaul further shortened the window and emphasized recency.
- **Frequency vs. absolute.** SMS is already frequency-based in one sense (violations per inspection, normalized by exposure), but every violation is a fixed, discrete hit. There is no notion of "context" or grace, and no positive credit — the best possible outcome is zero. That gap is exactly what TSV's design fills.
- **Consequences.** Percentile thresholds (roughly 65% for Unsafe Driving/HOS/Crash, higher for others) drive FMCSA prioritization. Shippers and insurers also read SMS percentiles directly.

Sources: csa.fmcsa.dot.gov SMS methodology and "What's Changing" documents; industry summaries (FleetCollect, CarrierOwl, Workplace Compliance Insights, 2026). Verify implementation status on the official portal before citing specifics.

**Design takeaway:** TSV deliberately diverges from CSA in three ways — (1) it scores the driver as a first-class entity, (2) it uses continuous decay instead of step cliffs, and (3) it allows scores to rise above baseline through verified positive behavior.

---

## 2. Event weighting and the driver score

Section 2.2–2.3 define per-event weight and decay. They apply to **both** ledgers: driver (HOS now, self-reported tailgating later) and company (observed tailgating). The driver score structure in 2.1 and trust credit in 2.4 are driver-only.

### 2.1 Driver score structure

```
S_driver = clamp( 800 + T − P_d , 0 , 1000 )
```

| Term | Meaning | Range |
|---|---|---|
| 800 | Starting point for a new driver — "unproven, not bad" | fixed |
| T | Trust credit earned by clean months | 0 … +200 |
| P_d | Decayed penalty mass from HOS events (+ self-reported tailgating in a future phase) | 0 … ∞ (clamped by score floor) |

A driver with no history starts at 800 and *earns* their way to 1000. A violation costs both P_d (immediate) and part of T (reduced credit), so recovery takes two forms: penalty decays, and trust rebuilds.

### 2.2 Penalty per event

Each violation event e contributes:

```
w_e = base[type] × tier_mult[e.tier] × freq_mult(e) × grace(e)
```

**Base weights and tiers**

| Type | base | Tier 1 (×1.0) | Tier 2 (×1.5) | Tier 3 (×2.5) |
|---|---|---|---|---|
| Tailgating | **60** | Headway <1.0 s sustained 5–15 s at ≥45 mph | Headway <1.0 s sustained >15 s, or 5–15 s at ≥60 mph | Headway <1.0 s sustained >15 s at ≥60 mph, or any <0.6 s sustained ≥5 s |
| HOS | **40** | ≤30 min over a limit; short/late break | 30 min–2 h over; 14-h window exceeded | >2 h over; 11-h driving limit; falsified or missing logs |

Headway here is *between the observed truck and the vehicle ahead of it*, computed by TSV from the range to each and the observed truck's speed (which TSV must estimate from host speed plus relative velocity).

**Scoring threshold is <1.0 s, full stop.** Headway between 1.0 and 2.0 s is logged as a *coaching observation* — visible to the driver and (in aggregate) to the company, never scored. Rationale: a scored event affects a career, so it must be egregious enough that a false positive is implausible. Below one second, a loaded tractor-trailer has no physical stopping margin at any highway speed; there is no honest argument that it was safe. Tiers then reflect exposure (duration × speed), not distance.

**HOS calibration target: one violation per quarter is the ceiling, zero is the goal.** The weights, the 90-day frequency window, and the absence of grace (below) are all set so that a driver with one tier-2 HOS violation in a quarter sits at the bottom of Good, two puts them in Watch, three in Intervention, four in High Risk. HOS regulations already contain the legitimate exceptions (adverse driving conditions, short-haul, sleeper split); a violation that made it onto the log had no exception to claim, so the score gives it none.

**Tailgating vs. HOS.** Tier-2 tailgating (90 pts) vs. tier-2 HOS (60 pts) is 1.5:1 per event, and the gap widens under repetition because tailgating's half-life is twice as long. **Why heavier:** tailgating is a *direct* crash mechanism — the truck is already in a state where a lead-vehicle brake event produces a rear-end collision with no recovery margin. HOS is a *probabilistic* risk proxy: fatigue raises crash likelihood but isn't itself the collision. One deliberate exception: a *first, isolated* tier-1/2 tailgating catch is graced to half (45 pts), which is lighter than a single HOS violation — because one sub-1-second observation can still be a single bad maneuver, while an HOS violation is a documented fact with the excuses already stripped out. In the POC these two types live on different ledgers (company vs. driver), so the ratio only becomes a direct within-score comparison when self-report arrives.

**Frequency multiplier** — the core "frequency, not absolute line" mechanism:

```
n = count of same-type events on the same ledger in trailing window, including this one
    window: tailgating 30 days, HOS 90 days (one calendar quarter)
    (company ledger: normalized to a 50-truck fleet, n = ceil(raw_count × 50 / N))
freq_mult = min( 1 + 0.3 × (n − 1) , 3.0 )
```

The 1st event in a window costs 1×, the 2nd 1.3×, the 5th 2.2×, capped at 3× from the 8th on. Repetition is what makes the penalty steep, not any single event. HOS uses the longer window because the tolerance is one per quarter — a second violation 60 days after the first is still "twice this quarter." The fleet-size normalization keeps a 500-truck carrier from being at 3× permanently just by having more trucks on the road.

**Grace (emergency allowance) — tailgating only:**

```
grace = 0.5  if type is TAILGATING and this is the first tailgating event on this ledger in 60 days AND tier ≤ 2
      = 1.0  otherwise (all HOS events, all tier-3 tailgating)
```

One isolated tier-1/2 tailgating catch every two months is half-price. A tier-3 event never gets grace — a 0.8-second headway at 65 mph is not an emergency maneuver, it is the emergency. HOS never gets grace: the regulations already grant the exceptions, and a violation is what's left after they've been applied.

### 2.3 Time decay

```
P = Σ over events  w_e × 0.5 ^ ( age_days / half_life[type] )
```

| Type | Half-life | Rationale |
|---|---|---|
| Tailgating | **180 days** | Habitual behavior, and TSV only samples it — each observed event likely represents many unobserved ones. Needs two clean quarters of evidence that it changed |
| HOS | **90 days** | One clean quarter to recover from a single violation; a pattern across quarters stacks |

Events are dropped from P entirely at **24 months** (matching FMCSA's window) — by then they're at <0.5% weight anyway. Raw events are retained for audit but no longer score.

### 2.4 Trust credit (driver recovery)

```
Each calendar month in which the driver has an active DriverEmployment record:
  no events on the driver ledger            → T += 20
  only tier-1 events, none repeated         → T += 10
  otherwise                                 → T += 0
On any HOS event:                       T −= 40   (floor 0)
On any self-reported tailgating event:  T −= 40   (floor 0)   [future phase]
T capped at 200
```

A clean driver goes 800 → 1000 in 10 months. The company ledger has no trust credit — it recovers through decay only, and through the program bonus in 3.3.

### 2.5 Bands

| Score | Band | Meaning |
|---|---|---|
| 900–1000 | Exemplary | Insurer discount tier; eligible for company incentive pools |
| 800–899 | Good | Baseline expectation |
| 700–799 | Watch | Company notified; coaching recommended |
| 600–699 | Intervention | Company must document a corrective action within 14 days |
| <600 | High risk | Counts as a "bad driver" in company aggregation; visible to DOT/insurer |

### 2.6 Worked example — tailgating

This example uses tailgating because it's the heavier, more interesting case. In the POC these events land on the **company** ledger (see 3.4 for how P_c enters the company score); in a future self-report phase the identical math lands on the driver. Shown here against a driver score for readability.

Start at 1000 (T = 200, P = 0), all events tier 2 (90 pts).

**A — one incident in 30 days.**
Grace applies (first in 60 days): w = 90 × 1.0 × 0.5 = 45. T drops to 160.
Score = 800 + 160 − 45 = **915**. After 180 days: P ≈ 22, T rebuilt to 200 (if clean since) → 978. Effectively forgiven in about two quarters.

**B — five incidents in 30 days.**
w₁ = 90 × 1.0 × 0.5 = 45 (grace)
w₂…w₅ = 90 × (1.3 + 1.6 + 1.9 + 2.2) = 630
P ≈ 675 (ignoring intra-month decay). T drops 5 × 40 → 0.
Score = 800 + 0 − 675 = **125**. Recovery: with zero further events, P halves every 180 days (338 → 169 → 84) and T rebuilds +20/month, so the score crosses 700 around month 9 and 900 around month 17. A bad month costs about a year and a half — proportionate to five sub-1-second catches, but not permanent. Remember these are *observed* events; five catches in a month implies constant behavior.

The same five events spread ~70 days apart each get grace (45 pts) and the frequency multiplier never fires — but trust credit can't out-rebuild an event every two months (−40 per event vs. +20 per clean month), so the score lands around **760, Watch**. That's the intended shape: 125 for a pattern, 760 for a recurring problem, 915 for a one-off.

### 2.7 Worked example — HOS on the driver ledger

Driver at 1000 (T = 200, P = 0). All violations tier 2 (60 pts), no grace, 90-day window.

| Violations this quarter | P | T | Score | Band |
|---|---|---|---|---|
| 1 | 60 | 160 | **900** | Good (bottom) |
| 2 | 60 + 78 = 138 | 120 | **782** | Watch |
| 3 | 138 + 96 = 234 | 80 | **646** | Intervention |
| 4 | 234 + 114 = 348 | 40 | **492** | High Risk |

Tier 1 (40 pts) runs one band gentler: 1 → 920, 2 → 828, 3 → 724 (Watch), 4 → 608 (Intervention). Tier 3 (100 pts) runs one band harsher: 1 → 860, 2 → 690 (Intervention). A driver with one tier-2 violation and then a clean quarter is back at ~985 by the end of it; a driver with one every quarter converges to swinging between ~840 (right after each violation) and ~940 (end of the clean stretch), which is the "ceiling, not goal" behavior — Good, never Exemplary, and never fully recovered.

---

## 3. Company aggregation algorithm

### 3.1 Structure

```
S_company = clamp( M − B − P_c + G , 0 , 1000 )
```

| Term | Meaning |
|---|---|
| M | Mean of driver scores (HOS-driven), weighted by months of active employment in trailing 90 days — the **baseline** |
| B | Non-linear bad-driver penalty |
| P_c | Company tailgating penalty mass from TSV-observed events, normalized for fleet size (see 3.4) |
| G | Verified safety-program bonus, 0 … +50 |

### 3.2 Bad-driver penalty (non-linear)

```
k = number of drivers with S_driver < 600, active in trailing 90 days
N = number of active drivers
B = ( k × (k + 1) / 2 ) × ( 50 / N )
```

The triangular term k(k+1)/2 gives exactly the requested curve for a 50-driver fleet:

| k bad of 50 | k(k+1)/2 | × 50/N | B |
|---|---|---|---|
| 1 | 1 | 1.0 | **1** |
| 2 | 3 | 1.0 | **3** |
| 3 | 6 | 1.0 | **6** |
| 5 | 15 | 1.0 | 15 |
| 10 | 55 | 1.0 | 55 |

The 50/N factor scales for fleet size: one bad driver in a 5-truck fleet is 20% of the operation and costs 10 points; one in a 500-truck fleet costs 0.1. Note M already falls when drivers score poorly, so B is a *surcharge for tolerating* known high-risk drivers, not the whole penalty. A company that fires or rehabilitates a driver gets B relief the moment they leave the <600 set — that is the pressure loop.

**Departure rule:** a bad driver who is terminated stops counting in k after 30 days; a bad driver who quits still counts for 30 days. This blocks the "let them quit right before the audit" dodge while not punishing a company indefinitely for a driver they removed.

### 3.3 Program bonus (scoring above baseline)

Each program is worth points only while **verified** (evidence uploaded and reviewed, or auto-verified from TSV data), and expires after 12 months unless renewed.

| Program | Points | Verification |
|---|---|---|
| Voluntary-break incentive (pays drivers for breaks beyond HOS minimums) | +10 | ELD data shows ≥X% of drivers taking bonus breaks |
| Coaching workflow (every Watch-band driver gets a logged coaching session within 14 days) | +15 | TSV audit of ScoreLedger vs. coaching records |
| Quarterly defensive-driving training | +10 | Attendance roster + attestation |
| OEM following-distance alerts acted upon (documented coaching on ≥90% of OEM headway alerts) | +10 | Alert log vs. coaching log audit — this targets the known failure mode of alerts reaching safety and dying there |
| Driver retention/pay floor program | +5 | Attestation |

Cap G at +50 so programs cannot mask bad outcomes: a fleet with M = 700 and k = 10 cannot buy its way to Good.

### 3.4 Company tailgating ledger (P_c)

Every TSV-observed tailgating event resolves to a vehicle → company and lands here, weighted and decayed exactly as in 2.2–2.3 (frequency multiplier normalized to a 50-truck fleet as noted there). The sum is then scaled so a fleet's score reflects *rate*, not raw count:

```
P_c = ( Σ decayed w_e ) × ( 50 / N )
```

For a 50-truck fleet that's the worked example in 2.6 verbatim: one observed event in a month costs 45 points, five cost ~675 — enough on its own to drop a 900 fleet to High Risk. A 500-truck fleet with the same five events loses ~41 — the fleet-size normalization applies to both the repeat count (5 × 50/500 rounds up to 1, so no frequency escalation) and the sum. A 5-truck fleet loses 6,750 → floored at 0, which is correct: five egregious catches in a month across five trucks is a company that should not have authority.

**What the company sees:** every event with plate, unit number if readable, timestamp, GPS, speed, headway, and the clip. The company knows who was driving. TSV does not ask, does not need to know, and does not adjust P_c based on whether the company acts. The pressure to act comes from the score staying down for months and from B climbing if that driver's HOS record is also poor.

**Companies with no drivers on file** (owner-operators, carriers that haven't registered drivers): M defaults to 800 and the score is effectively 800 − P_c + G. A single truck is a 1-truck fleet; the 50/N scaling makes each observed event count 50×, which is the intended outcome — there is nobody else to average against.

### 3.5 Update cadence

- Driver score: recomputed on every HOS event (real-time) and nightly for decay/T.
- Company score: recomputed on every observed tailgating event (real-time), whenever a driver crosses a band boundary, on roster changes, and nightly for decay.
- Monthly snapshot written to ScoreHistory for both; quarterly review recalibrates base weights against outcome data (crashes, near-misses).

---

## 4. Core data model

**Driver** — id, name, CDL number (hashed), current_score, trust_credit, penalty_mass, band, created_at

**Company** — id, name, USDOT number, current_score, baseline_M, bad_driver_penalty_B, tailgating_penalty_Pc, program_bonus_G, active_driver_count, active_vehicle_count, created_at

**DriverEmployment** — id, driver_id, company_id, start_date, end_date, separation_type (voluntary/terminated/null). One driver, many rows over time; this is what makes company changes work and what defines "active month" for trust credit.

**ObservedVehicle** — id, company_id (nullable until resolved), plate, plate_state, usdot_number, unit_number (if readable), VIN (if later matched), first_seen, last_seen. The thing the camera actually identifies.

**ObserverDevice** — id, host_company_id, host_vehicle_id, firmware_version, calibration_date, last_heartbeat. The TSV unit that saw the event.

**ViolationEvent** — id, ledger (DRIVER | COMPANY), type (TAILGATING | HOS), source (TSV_OBSERVED | ELD | ROADSIDE | SELF_REPORT), driver_id (driver ledger only), company_id, observed_vehicle_id (TSV-observed only), observer_device_id (TSV-observed only), tier, timestamp, gps_lat, gps_lon, road_segment, base_weight, tier_mult, freq_mult, grace, computed_weight, identification_confidence (0–1, TSV-observed only), status (active/disputed/voided), evidence_ref

**TailgatingDetail** — event_id, observed_speed_mph, range_to_observed_m, range_to_lead_m, min_headway_s, mean_headway_s, duration_s, lead_vehicle_cut_in (bool), weather_flag, clip_uri

**HOSDetail** — event_id, rule_violated (11h/14h/30min/60-70h), minutes_over, source (ELD/manual). HOS events don't come from TSV; they arrive from ELD/roadside data already tied to a CDL.

**ScoreHistory** — id, subject_type (driver/company), subject_id, timestamp, score, T, P_d (driver) or M/B/P_c/G (company), change_reason (event/decay/monthly_credit/roster/program/dispute), reference_id

**SafetyProgram** — id, name, points, verification_method, description

**CompanyProgramEnrollment** — id, company_id, program_id, enrolled_at, verified_at, verified_by, expires_at, evidence_uri, status

**DisputeCase** — id, event_id, filed_by, filed_at, reason, resolution (upheld/reduced/voided), resolved_by (DOT), resolved_at. A voided event is removed from P retroactively and a ScoreHistory correction is written.

**ExternalAccessLog** — id, company_id, accessor_type (DOT/shipper/insurer), accessed_at, scope. Accountability cuts both ways; companies should see who is pulling their score.

---

## 5. Edge cases and open questions

- **Driver changes companies.** The driver score (HOS ledger) belongs to the driver and travels with them. The old company's historical snapshots are never rewritten; the driver drops out of its M and k going forward (subject to the 30-day departure rule). The new company inherits the driver's *current* score in M immediately — hiring a 550 driver is a choice with a visible cost. Observed tailgating (P_c) stays with the company whose truck it was; it never follows the driver, because TSV never knew who the driver was.
- **Self-report phase (future, not POC).** If a truck with its own headway sensor reports its driver's tailgating, that event goes on the driver ledger at the same weights, and the company's P_c does *not* double-count it (the company already pays through M and B). Vehicle → driver mapping for self-report comes from the truck's ELD login, which is the same source as HOS. Nothing in the POC data model needs to change to add this later — the `source` field on ViolationEvent already distinguishes it.
- **Forgetting window.** Continuous decay means old events fade rather than vanish; the 24-month hard cutoff is for audit clarity and FMCSA parity. **Decided:** tailgating half-life is 180 days across all tiers — it's the strongest predictor of the crash TSV exists to prevent, and sampled observation means each catch under-represents actual behavior.
- **Identification confidence.** A scored event needs a plate or USDOT read that is unambiguous. Proposed: score only when identification_confidence ≥ 0.95 *and* the read resolves to exactly one registered company. Anything below that is retained as an unscored observation. Same certainty principle as the 1-second threshold — a wrong-company event is worse than a missed one.
- **Observation geometry.** TSV must estimate the observed truck's speed (host speed + relative velocity) and range to both the observed truck and its lead vehicle. Errors compound; the 5-second duration and <1.0 s threshold give margin, but the CV team should characterize headway error at 100–150 m range before any threshold is finalized.
- **Tailgating definition.** Time-headway based (not distance), computed by TSV from the observed truck's range to its lead vehicle and its estimated speed. Scored only at <1.0 s headway, sustained ≥5 s, above 45 mph (stop-and-go is not tailgating). Lead-vehicle cut-ins get a 4-second debounce — headway collapse caused by the other vehicle isn't the driver's event unless they fail to re-open the gap. Weather/low-visibility does *not* lower the scoring threshold (certainty principle holds) but does tighten the coaching-observation band. Adaptive cruise is a non-issue under this rule: no production ACC holds under 1 s. **Decided: 5-second minimum duration stays.** A 3-second window would catch a car that cuts in ahead of the truck to get around a slower vehicle — the truck is briefly under 1 s through no action of its own, and the gap opens as the car pulls away. Not safe, but not egregious, and not the driver's decision. Five seconds means the driver had time to react and chose not to.
- **HOS weighting.** Not all equal — tiered above. Fatigue inference is out of scope; HOS data comes from ELD/roadside, not TSV.
- **Disputes and false positives.** Every tailgating event ships with a clip. Dispute window 30 days; voided events are fully reversed. **Decided: DOT adjudicates.** TSV supplies evidence and never rules on its own events.
- **Cross-fleet fairness.** Out of scope for POC. Noted for later: CSA solves exposure differences with peer groups.
- **Gaming the company bonus.** Programs must be outcome-verified where possible, not attestation-only. Attestation-only programs should be worth less and audited randomly.
- **Score inflation.** With T capped at 200 and P unbounded, the ceiling is hard and the floor is soft. Confirm that's the intended asymmetry — it says "you can't be better than perfect, but you can be arbitrarily bad."
- **Data ownership and privacy.** Driver scores are personal data tied to a CDL. Who can query a driver's score outside their current employer — prospective employers? Insurers? This is a policy decision that shapes the ExternalAccessLog and consent model. The observer model adds a second question: the TSV host is recording other companies' trucks on public roads, which is legal, but the host company should have no access to the events its own trucks generate about competitors.
