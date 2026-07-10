# Cost Index estimator — design note

Status: **method chosen — manual in-sim CI tuning against real-world IAS.**
The tool serves clean real-world IAS-at-FL targets; the **sim does the CI inversion**. No FCOM /
table derivation needed. No SimBrief field write yet (out of scope until trusted).

## The method (the actual workflow)

1. Fly the route in the sim (FF 777), in cruise, at a real flight's flight level.
2. Get the **real-world cruise IAS** at that FL for a comparable flight (same route/operator).
3. **Tune the sim FMC CI** until the sim's cruise IAS sits in the real range.
4. Record that CI for the operator (→ eventually the airframe's default CI).

Example: sim flying IAS 280 @ FL330, real flight IAS 269–273 @ FL330 → lower CI until the sim
settles ~270.

**Key insight: the sim's FMC already maps CI→IAS, so the sim *is* the `(FL, IAS)→CI` table.**
That collapses the hard half of the original design — no FCOM cruise tables, no derived surface,
no self-cal curve, no absolute-scale anchor. All replaced by "tune to match." The CI you get is
"the CI that makes your sim fly real-world speeds," which is exactly the right target for a
sim-focused fleet, even where FF's CI scale isn't identical to real Boeing's.

## What the tool provides (its whole job)

A clean **real-world cruise IAS, per FL, per operator (and route)** — a stable target like
`FL330 → 269–273 kt (median, n=7 flights)` — so you tune against aggregated truth, not one noisy
FR24 track, and it works even when FR24 doesn't display IAS.

- **Source:** airplanes.live (free, broadcast `ias`) primary; ADSBExchange (paid, historical);
  FR24 IAS column when it happens to show it.
- **Filter** to cruise (alt ≥ FL290, |baro_rate| < 300 fpm), bin by FL, report median + spread.
- **Few datapoints suffice** — a handful of flights per operator/route gives a tight target.

## Why IAS (settled — do not re-litigate)

- Broadcast IAS is wind-clean and needs no temperature conversion at a fixed FL.
- **Real-world Mach reports are GS-derived → they carry wind** → that's why we use IAS. (A true
  broadcast Mach off Comm-B would be clean too, but IAS sidesteps having to adjudicate the source.)
- Groundspeed is gone — it's TAS ± wind.
- Mach↔IAS is pure standard atmosphere (altitude + temp); wind never enters that conversion.

## Accuracy — what to match, and the residual

For the tuned CI to be right, match the real flight's **conditions**, not just the IAS number:

- **FL** — match it. IAS at fixed CI varies strongly with FL.
- **Weight** — the sneaky one, and first-order. An **LRC table shows up to ~40 kt IAS spread at one
  FL** across the weight envelope — big enough to swamp the CI signal (flat-curve: ~5 kt = a wide CI
  band) if uncontrolled. Two caveats keep that number in its place:
  - LRC is a *weight-tracking* schedule by design (it chases the range optimum), so ~40 kt is closer
    to a **worst-case** weight sensitivity than to ours. Fixed-CI ECON also drops IAS as weight
    falls, but on a different, generally gentler curve within a realistic band — and we haven't
    measured *its* magnitude. Treat 40 kt as "weight *can* be this strong," **not** as our error bar.
  - **Why we're not sunk: step-climb.** A 777 occupies the FL that suits its *current* weight and
    climbs as it lightens, so at a fixed FL you observe a weight *window*, not full-vs-empty — which
    compresses that spread to a smaller (unmeasured) residual.
  - **So: compare like-for-like** — same route / stage-length (matches the weight *profile*) and same
    cruise phase (heavy early vs light late). Cross-operator IAS gaps at one FL are only safely read
    as CI *preference* when the weight profile lines up; that is exactly what the route/haul controls
    buy. A big weight mismatch gives a wrong CI even with a perfect IAS match.
- **Flat-curve caveat** — CI→IAS is nearly flat where airlines fly (~5 kt IAS spans a wide CI band),
  so small IAS differences imply large CI differences. How much of the observed spread is CI vs
  weight vs noise is **an open question — any "noise floor" figure is a hypothesis, NOT measured.**
  To measure it you'd hold operator+route+FL fixed and look at the spread of repeated observations;
  we haven't. So don't quote a CI error bar as fact.
- **Working assumption (pragmatic):** attribute the per-operator IAS-at-FL to that operator's
  **CI preference** and tune to it — don't decompose noise we can't yet measure. The report's
  `op × type × [tier] × FL → IAS` table *is* the operator-CI-preference view.
- **Measurement noise** (turbulence, small corrections) is ~zero-mean → the median target absorbs it.

## Cross-check — OpenAP (open aircraft-performance model)

Sanity-checked the collected IAS against an **independent, open** perf model:
[OpenAP](https://github.com/junzis/openap) (`pip install openap`, MIT, ADS-B-derived; models B77W & B772,
not B77L/B77F). Throwaway script only — **not** wired into `ci_collect.py` (keeps its stdlib-only rule).
Computed the B77W econ cruise band (MRC → LRC, from OpenAP's drag/fuel model) per FL and compared to the
collected medians.

**Result — every collected FL median falls inside the econ band**, and the *implied* cruise weight (the
weight whose MRC..LRC band contains the observed IAS) drops monotonically with FL:

    FL290 ~235-285t · FL310 ~220-265t · FL330 ~200-240t · FL350 ~180-220t · FL370 ~170-205t

That descending column **is the step-climb / optimum-locus effect, visible in real data** — heavy down low,
light up high, all realistic 777-300ER cruise weights. It empirically backs the "weight window per FL"
claim in Accuracy above: at a fixed FL you see a *narrow* weight window, not the full envelope — which is
why like-for-like (route + FL) cross-operator comparison is viable.

**What it buys / doesn't:** buys (1) confidence the pipeline emits physically sane targets, (2) evidence for
the weight-window argument, (3) an implied-weight read to check a real flight is at a comparable weight to
the sim. Does **not** buy a CI — the econ band is wide (~25-30 kt MRC→LRC); operator CI differences live
*inside* it and OpenAP can't resolve which CI. OpenAP's CI scale (0–100) ≠ Boeing (0–9999) ≠ FF, so tuning
to IAS stays the method. Caveats: OpenAP is itself data-fit (not Boeing's FMC PDB); band edges are
approximate (LRC + ~6 kt); implied weight is coarse (±~25 t).

## Later: automate the read (optional, not needed now)

The manual method needs no table. If you ever want the tool to output CI directly (no manual
tuning), **generate the table from the sim once**: fly at CI 20 / 40 / 60 / … and record IAS@FL →
that's your `(CI, weight, FL)→IAS` surface, built from the exact sim you fly. The sim replaces the
FCOM. Then observed IAS → CI automatically. Future enhancement.

**Working assumption (user's, to verify on calibration): FF CI scale == Boeing CI (0–9999).**
Distinguish two things:
- *CI scale* (what the number means) — believed to match; FF is study-level.
- *CI response* (the speed the number produces) — still rides on FF's fuel/EPR model (~2–3% off real
  thrust per CLAUDE.md), so FF-CI-X flies *almost* the real-CI-X speed, not exactly. Tune-to-IAS
  absorbs this; setting a published CI blind does not.

If the scale holds, then: (1) published airline CI values become a usable **starting bracket /
coverage fallback** (sources are sparse & stale — hint, not truth); (2) the CI recovered by inverting
observed IAS through the FF calibration is on the **real scale** — an estimate of the airline's actual
CI (still a *band*, not a point: weight-window + flat curve); (3) tuned CI vs published CI is a
**cross-check**. It does **not** remove the need for the FF calibration curve (scale-match ≠ having
CI→IAS; no web source carries CI→speed). **Testable:** once calibrated, compare FF-CI-X speed to a
published real-CI-X point — agreement confirms scale + response.

## Data source fields (confirmed)

airplanes.live / ADSBExchange readsb JSON expose: `ias`, `tas`, `mach`, `ws`, `wd`, `oat`.
We use **`ias`**. Rate limit: airplanes.live 1 req/s, live snapshots (accumulate by polling).

## Links

- airplanes.live REST field descriptions: https://airplanes.live/rest-api-adsb-data-field-descriptions/
- ADSBExchange v2 API fields: https://www.adsbexchange.com/version-2-api/
- Standard-atmosphere airspeed conversion (background, Mach↔CAS↔TAS): https://aerotoolbox.com/airspeed-conversions/
- Airline cost-index community list (sanity cross-check for tuned values): https://costindex-index.fandom.com/wiki/Different_Cost_indexes_from_ALOT_of_airlines

## Status / open

- **Observation side: BUILT** — `ci_collect.py`:
  - `collect` polls airplanes.live for airborne 777s, keeps clean cruise+IAS samples to
    `ci_samples.jsonl` (verified: one 1-min run → ~337 777s, 445 samples).
  - `enrich` resolves each callsign → route → O/D countries via hexdb.io into `route_cache.json`
    (verified: 138/150 callsigns, 92%). Callsign is captured at collect time, so route is derived
    later with no data lost.
  - `report` prints operator × type × FL → IAS median/range/n; `--haul` splits by coarse tier
    **domestic / regional / intl** (orig==dest country / same continent / else).
- **Data model:** capture only knowns — IAS, FL, and route. **No weight** (unknown even on a fixed
  route; payload varies) — the user's heuristics own weight reconciliation. Haul tier is coarse by
  design (no EU-vs-US split); the ISO2→continent map in `ci_collect.py` is adjustable.
- **Reconciliation side: user-owned** — match a target in the sim (FL + comparable weight/route),
  tune FMC CI until sim IAS lands in the range.
- FCOM fetch: **no longer required** (the sim is the table). Dropped.
- Known gap: operators whose callsign doesn't parse to a 3-letter ICAO prefix show as `???` (a few
  private/ferry tails). Could add a registration→operator fallback later; low priority.
- Open: how long to accumulate (longer run → more flights per FL → tighter targets); free
  airplanes.live polling is fine (few datapoints needed).
