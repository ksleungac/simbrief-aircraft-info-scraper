# SimBrief B777 Fleet Builder

## What this is
SimBrief can't save fleets/airframes via API. This project **collects airframe data**
for a registration and stages it in a worksheet so the user **manually pastes each row
into SimBrief's custom-airframe editor**. The tool collects; the user pastes.

- **Scope: Boeing 777 family only** (for now).
- **Sim target: FlightFactor 777 (X-Plane)** — matters for the thrust field (below).

## One command
```
python collect.py <REG> [callsign] [aircraft_icao]      # single
python collect.py --batch <REG1> <REG2> ...             # many, one browser session, walk away
```
Auto-detects operator/type, scrapes everything it can, **upserts a row into `fleet.json`
keyed by registration**, then rebuilds `SimBrief_B777_Fleet.xlsx`. Optional args override
auto-detection (e.g. `python collect.py JA784A ANA B77W`).

It is **hardened to run unattended**: every external step is wrapped; on failure it records
a flag and carries on — it never crashes. In `--batch`, one bad tail can't kill the run
(each row is written immediately; a fatal row gets a stub + flag). The sheet renders once at the end.

**Notes split into two classes:** `FLAGS:` = action needed → Status `Check`; `INFO:` =
informational (auto-resolved) → Status stays `Ready`. A known-operator tail (engine + cabin
auto-resolved, exact edi-gla plan) comes out **`Ready` / CLEAN** — only OEW/Max Cargo remain.

**Auto-resolution (removes most sit-in):**
- **Cabin:** full-conversion fleets auto-pick latest silently (`CABIN_AUTO_LATEST`, e.g. CPA→Aria,
  KLM→PremComfort). Only fleets with holdouts (e.g. ANA 'The Room') still flag for per-tail confirm.
- **B772 engine** (the only multi-engine base type): resolved via `OPERATOR_ENGINE_B772` (cosmetic;
  thrust spread ~4%, immaterial under P00). Operators not mapped still flag.

## Field ownership (who fills what)
- **Input (you):** Registration — the key.
- **Script (web/static):** Operator, Base Type, Variant, Airframe Name, Hex, SELCAL,
  Equip 10a/10b, PBN, Engine (real+sim), Thrust, Units, MZFW/MTOW/MLW/Max Fuel, Max Pax.
- **You (manual, always):** `OEW`, `Max Cargo`. Plus the **cabin-layout choice** only for
  fleets with holdout configs (e.g. ANA 'The Room'); full-conversion fleets auto-resolve.

## Files
- `collect.py` — the orchestrator (Playwright, one browser session for all sources).
- `static_data.py` — units rule, weight table, engine→thrust, name builder, perf defaults.
- `equip_codes.py` — ICAO 10a/10b/PBN code→meaning reference + decoder.
- `build_sheet.py` — renders `fleet.json` → `SimBrief_B777_Fleet.xlsx` (4 tabs). Run alone to re-render.
- `edigla_extract.py` — standalone edi-gla extractor (collect.py has the same logic inline).
- `edigla_capture.py` — exploratory page-dumper; run this to **re-learn edi-gla's layout** if it changes, or to **re-login**.
- `rzjets_extract.py` — standalone rzjets per-tail lookup (SELCAL/engine/cn/ln/delivery + rego history). Headful.
- `rzjets_capture.py` — rzjets structure probe / **Cloudflare clearance refresh** (run + click the Turnstile once).
- `fleet.json` — **source of truth** (list of airframe records). Edit here, then `build_sheet.py`.
- `SimBrief_B777_Fleet.xlsx` — output. Tabs: Fleet / 777 Reference / Field Map / Equipment Codes.
- `.edigla-profile/` — Playwright **persistent login** for edi-gla. Don't delete/share. Holds the session.
- `.rzjets-profile/` — Playwright profile holding the **Cloudflare clearance cookie** for rzjets. Don't share.
- `edigla_capture/`, `edigla_out/`, `rzjets_out/` — dumps for debugging.

## Sources (and order of preference)
- **Hex (Mode-S/ICAO24):** `airport-data.com/aircraft/{REG}.html` (also gives operator, type, c/n, year). Public.
- **SELCAL + Equip 10a/10b + PBN:** **edi-gla** (login). The reg lives in the **Field-18 RMK**, so use the
  remarks "contains" filter: `Flightplan[remarks]=REG/{reg}` (no direct reg search). **Exact-reg match
  FIRST**, then pick the **newest** matching plan (max flightplan id).
  - **Modern-format plan → real 10a/10b/PBN.** Old-format plan shows `/S` (blank 10a) → SimBrief default for 10a (keep 10b/SELCAL).
  - **Pitfall (handled in code):** if NO exact-reg plan, **never borrow SELCAL** (per-tail). Only borrow
    equip/PBN from a same-operator/same-type **sibling** (vintage-cohort) and only with a loud flag —
    ideally the closest delivery/line number, not just the newest. The fallback that blindly took the
    first/newest other-tail plan was the bug.
- **rzjets (cross-check / SELCAL fallback):** per-tail SELCAL, engine, cn/ln, delivery + **registration
  history**. Cloudflare-Turnstile gated → runs **headful** reusing `.rzjets-profile` clearance (refresh with
  `rzjets_capture.py` + one click). **Opt-in via `RZJETS=1`** so default headless runs never hang. In code it:
  fills SELCAL when edi-gla has no exact plan, fills cn/ln/delivery, cross-checks B772 engine, and **flags a
  FORMER rego** (e.g. B-KQD search → airframe now `ZK-OKV`/Air NZ → that's why edi-gla had no plan).
  Clean extraction: rzjets links a rego id in BOTH `?reg=<id>` and `?sel=<id>`, so SELCAL maps to the exact tail.
- **Cabin:** layered resolver (flyings.net is dead, dropped). NO free source maps a registration to its
  current cabin (sub-fleet configs drift per-tail), so resolve by **operator+type**:
  1. **curated `CABIN_CONFIGS`** in `static_data.py` (authoritative, marks `latest`, extend as fleet grows),
  2. **live seatmaps.com** scrape (operators not yet curated; stable/structured, real source),
  3. always **default latest, list every candidate in Notes, flag "confirm tail."**
  - **Forward-valid policy (do not re-litigate):** if a fleet is undergoing **full conversion** to a new
    config, use the **forward-valid (new)** config even for tails not yet converted (e.g. **Cathay → 77J Aria**,
    whole 777 fleet converting by 2027). If the new product is **NOT** expected on a tail soon, keep its
    **current** config (e.g. **ANA JA792A → old 68J**; "The Room" not coming to the 3 holdout tails soon).
  - planespotters/airfleets carry no per-tail seat counts; rzjets has them but is Cloudflare-Turnstile gated.
- **Weights / thrust / units / name:** `static_data.py` (no web).

## edi-gla specifics
- **No public API.** Has a human-driven "SIMBRIEF" export button. Login can't be scripted →
  **persistent Playwright profile**: user logs in by hand once (run `edigla_capture.py`), session persists.
  If a run flags "edi-gla NOT logged in", re-run `edigla_capture.py` and log in again.
- Search form: `GET /flightplan/search`, fields `Flightplan[callsign]`, `Flightplan[aircraft_icao]`,
  `Flightplan[remarks]`, sort `fpl_id`.
- Flight plan page `/flightplan/{id}`: labels `Aircraft`, `Equipment` (filed as `10a/10b`, split on `/`;
  empty left side = old format), `Remarks` (Field 18: `REG/ SEL/ NAV/ PBN/ DAT/`).

## Conventions & decisions (do not re-litigate)
- **SimBrief 777 base types:** `B772` (777-200 AND 200ER), `B77W` (300ER), `B77L` (200LR), `B77F` (777F).
  **No B773** (777-300 classic has no SimBrief profile) — out of scope.
- **777-200 basic = 200ER with reduced MTOW + Max Fuel only** (other weights = ER values).
- **Units:** `LB` for **US / Canada / Japan** registrations, `KG` everyone else (by reg prefix).
  Weights stored in the row's unit (kg→lb converted, rounded to 100).
- **Airframe Name:** `FF {airline-ICAO} [ER] {cabin}` — e.g. `FF CPA C45Y291`, `FF ANA F8C64W24Y116`.
  - `FF` = FlightFactor (addon marker). `ER` tag **only** for 777-200ER (everything else: base type field disambiguates).
  - Cabin code = `F`/`C`/`W`/`Y` + counts (First/Business/PremEcon/Economy).
  - **Don't repeat Registration or Base Type** in the Name — they're separate SimBrief fields.
- **Variant column** = full customer-code type for reference (e.g. `777-381ER`, `777-267`). NOT a SimBrief
  field (SimBrief uses the ICAO base type). Boeing middle digits = customer code (81=ANA, 67=Cathay); retired ~2016.
- **Thrust** = SimBrief "Takeoff Thrust Flat Rating", per ONE engine, lbf. **Align to the SIM (FlightFactor),
  not the real engine.** Engine NAME stays real (cosmetic). VERIFIED actual ratings (not name-inferred):
  Trent892 **91450**, GE90-94B **93700**, PW4090 **90000**, GE90-115B **115300**, GE90-110B1 **110100**.
  (e.g. B-HND real Trent 877 → sim Trent 892 → thrust 91450.)
- **Engine by base type:** B77W→GE90-115B, B77L/B77F→GE90-110B1 (single option). **B772 has 3 options**
  (GE90-94B / PW4090 / Trent892) → needs per-tail check (a flag).
- **Fuel Factor = `P00`** (no adjustment; pending in-sim calibration).
- **Cost Index** = SimBrief base-type default (varies by airline; hard to source).
- **Service ceiling FL431, cruise level offset 0** (defaults; leave).
- **PBN specs are NOT nested by number** (RNAV10/RNP10 = oceanic, needs GNSS/time-limited INS; RNAV5 =
  continental). A tighter spec covers a looser one only in the same domain (RNP4⇒RNP10). **Take the filed
  PBN — don't infer the ladder.**
- **SimBrief airframe editable fields:** weights, equipment (10a/10b), PBN, service ceiling, cruise level
  offset, fuel factor, takeoff thrust flat rating, default CI/profiles, pax/bag weights. **No engine field**
  (baked into base type). **No per-airframe Remarks** — RMK/Field-18 (`DAT/`, `CPDLC/`) is a *flight-plan*
  field (Flight Options → custom Field-18 table), low priority.

## FlightFactor 777 v2 — engines actually simulated
Thrust aligns to the engine **FF actually runs** (FF uses an EPR-based thrust model, ~2–3% of real),
NOT the real-world tail's engine. Engine NAME in the sheet stays real (cosmetic).

Released v2 aircraft + Engine Expansion Pack (777EE, ~$15), as of mid-2026:
- **777-200ER (B772)** — 3 engines modelled:
  - **GE90 base** — `GE90-94B` (user-confirmed; store page agrees; one review mislabeled it -90B). **93700 lbf**.
  - **PW4090** (expansion) — EPR ~3% of real. ~90000 lbf.
  - **Trent 892** (expansion, added Sep 2025) — EPR/thrust ~2% of real. **91450 lbf**.
  - FF does **NOT** model Trent 877/884/895 → a real Trent-877 tail (e.g. B-HND) uses **892 / 91450**.
- **777F / 777-300ER / 777-200LR** — real engines `GE90-115B` (300ER, **115300**) /
  `GE90-110B1` (200LR/F, **110100**). Freighter Upgrade is released; FF v1 modelled all variants but
  **v2 is being rebuilt variant-by-variant** — confirm a given variant's v2 package exists before
  trusting it as "modelled".
- Roadmap: expansion grows to 27 engine models / 18 types.

Verified rated thrust (lbf), name-independent (don't infer from the number in the name):
`Trent892 91450` · `GE90-94B 93700` · `PW4090 90000` · `GE90-115B 115300` · `GE90-110B1 110100`.

## Operating model
Hybrid by design: **script does the bulk unattended; I (Claude) step in for format drift and judgment.**
"I step in" cases: cabin config (multiple layouts), B772 engine family, scraped-site format changes,
operators missing from `OPERATOR_ICAO` / `ICAO_NAME` in `collect.py` (extend those dicts as the fleet grows).

## Environment
Windows. Python 3.14 (user install). `playwright` + chromium installed, `openpyxl` installed.
Set `HEADLESS=1` to run the browser headless.

## Status
Rows done: **B-HND** (Cathay 777-200, old-format → equip defaulted) and **JA784A** (ANA 777-300ER,
modern-format → real edi-gla 10a/10b/PBN). Both **pending OEW + Max Cargo** from the user.
