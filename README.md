# SimBrief B777 Fleet Builder

SimBrief can't save fleets/airframes via its API. This tool **collects Boeing 777
airframe data for a registration** and stages it in an Excel worksheet so you can
**manually paste each row into SimBrief's custom-airframe editor**. The tool collects;
you paste.

- **Scope:** Boeing 777 family only.
- **Sim target:** FlightFactor 777 (X-Plane) — drives the thrust field (aligned to the
  engine FF actually simulates, not the real-world engine; the engine *name* stays real).

## Install (uv)

```bash
uv sync                          # create venv + install playwright, openpyxl
uv run playwright install chromium   # one-time: fetch the browser binary
```

## One command

```bash
uv run python collect.py <REG> [callsign] [aircraft_icao]   # single
uv run python collect.py --batch <REG1> <REG2> ...          # many in one session
```

Auto-detects operator/type, scrapes what it can, **upserts a row into `fleet.json`
keyed by registration**, then rebuilds `SimBrief_B777_Fleet.xlsx`. Optional args
override auto-detection, e.g. `uv run python collect.py JA784A ANA B77W`.

Notes split into `FLAGS:` (action needed → Status `Check`) and `INFO:` (auto-resolved
→ stays `Ready`). A known-operator tail comes out `Ready`/CLEAN — only OEW/Max Cargo left.
`--batch` reuses one browser session and isolates failures (one bad tail can't kill the run).

It is **hardened to run unattended**: every external step is wrapped; on failure it
records a flag in the row's Notes and carries on — it never crashes. A partial row is
always written.

Re-render the sheet without scraping:

```bash
uv run python build_sheet.py
```

## edi-gla login (one-time, manual)

edi-gla has no public API and login can't be scripted, so the project uses a
**persistent Playwright profile**. Log in by hand once:

```bash
uv run python edigla_capture.py     # opens a browser; sign in; the session persists
```

The session lives in `.edigla-profile/` — **git-ignored, never published.** If a run
flags "edi-gla NOT logged in", re-run the command above and sign in again.

## Field ownership (who fills what)

- **You (input):** Registration — the key.
- **Script (web/static):** Operator, Base Type, Variant, Airframe Name, Hex, SELCAL,
  Equip 10a/10b, PBN, Engine (real + sim), Thrust, Units, MZFW/MTOW/MLW/Max Fuel, Max Pax.
- **You (manual):** `OEW`, `Max Cargo`, and the **cabin-layout choice** when an operator
  runs multiple configs (the script defaults to the latest; you confirm).

## Files

| File | Role |
|---|---|
| `collect.py` | The orchestrator (one Playwright session for all sources). |
| `static_data.py` | Units rule, weight table, engine→thrust, name builder, perf defaults. |
| `equip_codes.py` | ICAO Item 10a/10b/PBN code reference + decoder. |
| `build_sheet.py` | Renders `fleet.json` → `SimBrief_B777_Fleet.xlsx` (4 tabs). |
| `edigla_extract.py` | Standalone edi-gla extractor (same logic lives inline in collect.py). |
| `edigla_capture.py` | Page-dumper; run to (re)learn edi-gla's layout or to re-login. |
| `rzjets_extract.py` | Standalone rzjets per-tail lookup (SELCAL/engine/cn/ln/delivery + rego history). |
| `rzjets_capture.py` | rzjets probe / Cloudflare-clearance refresh (run + click the Turnstile once). |
| `fleet.json` | **Source of truth** (list of airframe records). Edit, then `build_sheet.py`. |
| `SimBrief_B777_Fleet.xlsx` | Output (git-ignored; regenerate from `fleet.json`). |

## Sources (order of preference)

- **Hex / operator / type:** `airport-data.com` (public).
- **SELCAL + Equip 10a/10b + PBN:** **edi-gla** (login). The registration lives in the
  Field-18 RMK, so the search filters remarks `contains REG/<reg>`. Exact-reg match first,
  then the newest matching plan. Modern-format plan → real 10a/10b/PBN; old-format → blank
  10a (SimBrief default). SELCAL is per-tail and is **never** borrowed from another tail.
- **Cabin:** curated `CABIN_CONFIGS` table → live `seatmaps.com` fallback (operator+type configs;
  default latest, list candidates, flag for confirm). flyings.net is dead/dropped.
- **rzjets (opt-in `RZJETS=1`):** per-tail SELCAL/engine/cn/ln/delivery + registration history.
  Cloudflare-gated → runs headful via `.rzjets-profile` (refresh clearance with `rzjets_capture.py`).
  Fills SELCAL when edi-gla has no exact plan, and flags a *former* registration (airframe re-registered).
- **Weights / thrust / units / name:** `static_data.py` (no web).

## Notes

- SimBrief 777 base types: `B772` (777-200/200ER), `B77W` (300ER), `B77L` (200LR),
  `B77F` (777F). No B773 (777-300 classic has no SimBrief profile).
- Units: `LB` for US / Canada / Japan registrations, `KG` everyone else.
- See `CLAUDE.md` for the full set of locked conventions and decisions.
