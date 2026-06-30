"""
SimBrief B777 fleet builder - STATIC DATA (DRAFT, pending user confirmation).

Sim target: FlightFactor 777 v2 (X-Plane). FF models these engines:
  GE90-94B, PW4090, Trent 892 (classics)  +  GE90-115B (300ER), GE90-110B1 (200LR/F).

Rule for the THRUST field (SimBrief "Takeoff Thrust Flat Rating", per ONE engine, lbf):
  align to the SIM's modelled engine, NOT the real tail.
  -> real B-HND is Trent 877, but in FF it's Trent 892, so thrust = 92,000.
  Engine NAME stays real (cosmetic); only the thrust number tracks the sim.

NOT here (per-tail web lookup): operator, variant, real engine, hex, SELCAL.
User-supplied per tail: OEW, Max Pax, Max Cargo.
"""

# ---------------------------------------------------------------------------
# 1) UNITS RULE  - LBS for US / Canada / Japan, KGS everyone else (by reg prefix)
# ---------------------------------------------------------------------------
LBS_COUNTRIES = {"United States", "Canada", "Japan"}
PREFIX_COUNTRY = {
    "N": "United States", "C-": "Canada", "CF-": "Canada", "JA": "Japan",
    "B-": "Hong Kong / China / Taiwan / Macau",   # -> KG
}

def units_for_registration(reg: str) -> str:
    reg = reg.upper().strip()
    for pfx in ("CF-", "C-", "JA", "N", "B-"):       # longest-first
        if reg.startswith(pfx):
            return "LB" if PREFIX_COUNTRY[pfx] in LBS_COUNTRIES else "KG"
    return "KG"

# ---------------------------------------------------------------------------
# 2) ENGINE -> THRUST (sim-aligned).  real_name -> (real_lbf, ff_name, ff_lbf)
#    ff_lbf is what goes in SimBrief's Takeoff Thrust Flat Rating.
# ---------------------------------------------------------------------------
# ff_lbf = VERIFIED rated takeoff thrust (NOT inferred from the name).
#   Trent 892 -> 91,450 (not 92,000) | GE90-115B -> 115,300 rated (115,540 max cert)
#   GE90-94B -> 93,700 | GE90-110B1 -> 110,100 (110,760 max) | PW4090 -> 90,000
ENGINES = {
    "Trent 877": (76400,  "Trent 892", 91450),   # real B-HND; FF models 892
    "Trent 884": (84500,  "Trent 892", 91450),
    "Trent 892": (91450,  "Trent 892", 91450),
    "Trent 895": (93400,  "Trent 892", 91450),
    "GE90-90B":  (90000,  "GE90-94B",  93700),
    "GE90-94B":  (93700,  "GE90-94B",  93700),
    "PW4090":    (90000,  "PW4090",    90000),
    "PW4098":    (98000,  "PW4090",    90000),    # -300 classic (out of scope)
    "GE90-115B": (115300, "GE90-115B", 115300),
    "GE90-110B1":(110100, "GE90-110B1",110100),   # -200LR / -F
}

def thrust_for_engine(real_engine: str):
    """returns (ff_engine_name, takeoff_thrust_flat_rating_lbf)"""
    e = ENGINES.get(real_engine.strip())
    return (e[1], e[2]) if e else (None, None)

# ---------------------------------------------------------------------------
# 3) NOMINAL WEIGHT TABLE  (kg; max certified).  Keyed by SimBrief base type.
#    777-200 basic = B772 with reduced MTOW + MaxFuel only (per user).
#    Single-engine types carry a fixed thrust; classics get thrust from ENGINES.
# ---------------------------------------------------------------------------
WEIGHTS_KG = {
    "B772": {            # 777-200 / 777-200ER  (one profile)
        "label": "777-200ER", "icao": "B772", "engine_choice": ["GE90-94B","PW4090","Trent 892"],
        "MTOW": 297560, "MLW": 213180, "MZFW": 195040, "MaxFuel": 138900, "FuelL": 171176,
        # basic 777-200 override:
        "_200_basic": {"MTOW": 247210, "MaxFuel": 94240, "FuelL": 117348},
    },
    "B77W": {            # 777-300ER
        "label": "777-300ER", "icao": "B77W", "engine_choice": ["GE90-115B"],
        "MTOW": 351535, "MLW": 251290, "MZFW": 237683, "MaxFuel": 145540, "FuelL": 181283,
    },
    "B77L": {            # 777-200LR
        "label": "777-200LR", "icao": "B77L", "engine_choice": ["GE90-110B1"],
        "MTOW": 347815, "MLW": 223168, "MZFW": 209556, "MaxFuel": 145540, "FuelL": 181283,
    },
    "B77F": {            # 777F
        "label": "777F", "icao": "B77L", "engine_choice": ["GE90-110B1"],
        "MTOW": 347815, "MLW": 260816, "MZFW": 248115, "MaxFuel": 145540, "FuelL": 181283,
    },
}
KG_TO_LB = 2.20462

# ---------------------------------------------------------------------------
# 4) DEFAULT ICAO EQUIPMENT (proposal; SimBrief auto-fills from base type,
#    override only when edi-gla shows the real tail differs)
# ---------------------------------------------------------------------------
DEFAULT_EQUIP_777 = {"10a": "SDE2E3FGHIJ2J3J4J5M1RWXYZ", "10b": "LB1D1", "PBN": "A1B1C1D1L1O1S2"}

# ---------------------------------------------------------------------------
# 5) PERFORMANCE / OPTION FIELDS in the SimBrief airframe editor
#    status: AUTO = base-type default (leave) | YOU = your preference (pending)
# ---------------------------------------------------------------------------
PERF_DEFAULTS = {
    "service_ceiling_ft": 43100,   # AUTO  (777 default ~FL431)
    "cruise_level_offset": 0,      # AUTO  (leave 0 unless you fly odd levels)
    "fuel_factor": "P00",          # set: no adjustment yet, pending in-sim calibration
    "default_cost_index": None,    # leave base-type default (varies by airline, hard to source)
    "climb_profile": None,         # accept base-type default
    "cruise_profile": None,        # accept base-type default
    "descent_profile": None,       # accept base-type default
    "pax_weight_kg": 79,           # SimBrief default
    "bag_weight_kg": 25,           # SimBrief default
}

# Airframe NAME convention -> SimBrief "Name" field.
# Reg + base type are SEPARATE fields, so do NOT repeat them. Pack info not stored
# elsewhere: addon, airline, the ER tag (only 200/200ER share base type B772), cabin.
#   "FF {icao} [ER] {cabin}"   e.g.  "FF CPA C45Y291"  /  "FF CPA ER C45Y291"
#     FF     = FlightFactor (addon marker)
#     icao   = 3-letter airline ICAO   (CPA)
#     ER     = ONLY for the 777-200ER (basic 200 + all other base types: no tag)
#     cabin  = class+count, F/C/W/Y    (C45Y291 = 45 business, 291 economy)
NAME_FORMAT = "FF {icao} [ER] {cabin}"

def airframe_name(icao: str, cabin: str, is_200er: bool = False) -> str:
    tag = "ER " if is_200er else ""
    return f"FF {icao} {tag}{cabin}".strip()

# ---------------------------------------------------------------------------
# 6) CABIN CONFIGS  - the weak field. NO free source maps a registration to its
#    current cabin (sub-fleet configs drift per-tail, mid-retrofit), so:
#      curated table (authoritative, marks 'latest')  ->  live seatmaps.com scrape.
#    Resolver ALWAYS defaults to latest, lists every candidate, and flags the run
#    so you confirm the actual tail. code uses F/C/W/Y (First/Business/PremEcon/Econ).
#    Extend CABIN_CONFIGS as the fleet grows (same pattern as OPERATOR_ICAO).
#    Numbers verified Jun 2026 (seatmaps.com / aerolopa / airline sites).
# ---------------------------------------------------------------------------
CABIN_CONFIGS = {
    ("ANA", "B77W"): [
        {"code": "F8C64W24Y116", "pax": 212, "label": "'The Room' new 64J", "latest": True},
        {"code": "F8C68W24Y112", "pax": 212, "label": "original staggered 68J"},
    ],
    ("CPA", "B77W"): [
        {"code": "C45W48Y268",   "pax": 361, "label": "77J Aria Suites, 3-class retrofit (no First)", "latest": True},
        {"code": "F6C53W34Y201", "pax": 294, "label": "77A 4-class (with First)"},
        {"code": "C40W32Y296",   "pax": 368, "label": "77K 3-class (Cirrus II, no First)"},
    ],
    ("CPA", "B772"): [
        {"code": "C45Y291", "pax": 336, "label": "regional 2-class (Cirrus, no First)", "latest": True},
    ],
    ("KLM", "B772"): [
        {"code": "C35W24Y229", "pax": 288, "label": "new 3-class (Premium Comfort)", "latest": True},
        {"code": "C34Y286",    "pax": 320, "label": "old 2-class"},
    ],
}

# operator ICAO -> seatmaps.com airline slug (live fallback for ops not curated above)
SEATMAPS_SLUG = {
    "CPA": "cx-cathay-pacific", "ANA": "nh-ana", "JAL": "jl-japan-airlines", "KLM": "kl-klm",
    "UAL": "ua-united-airlines", "AAL": "aa-american-airlines", "DAL": "dl-delta-air-lines",
    "BAW": "ba-british-airways", "UAE": "ek-emirates", "QTR": "qr-qatar-airways",
    "SIA": "sq-singapore-airlines", "KAL": "ke-korean-air", "AFR": "af-air-france",
    "EVA": "br-eva-air", "CAL": "ci-china-airlines", "ANZ": "nz-air-new-zealand",
    "THY": "tk-turkish-airlines", "SWR": "lx-swiss", "ACA": "ac-air-canada",
    "ETD": "ey-etihad-airways", "AIC": "ai-air-india", "CES": "mu-china-eastern",
    "CSN": "cz-china-southern",
}
SEATMAPS_TYPE = {"B772": "boeing-777-200er", "B77W": "boeing-777-300er", "B77L": "boeing-777-200lr"}

def cabin_candidates(icao, base):
    """Curated cabin configs for (operator ICAO, base type). [] if none."""
    return CABIN_CONFIGS.get((icao or "", base or ""), [])

def pick_latest(configs):
    """The config flagged latest, else the first."""
    if not configs:
        return None
    for c in configs:
        if c.get("latest"):
            return c
    return configs[0]

# operator+type combos where LATEST is forward-valid for the WHOLE fleet (full
# conversion or single product) -> auto-pick latest silently, NO confirm flag.
# Combos NOT listed (with >1 config) still flag for per-tail confirmation,
# e.g. ANA/B77W (holdout tails without 'The Room').
CABIN_AUTO_LATEST = {
    ("CPA", "B77W"),   # entire 777 fleet converting to 77J Aria by 2027
    ("KLM", "B772"),   # Premium Comfort retrofit fleet-wide (done ~Apr 2026)
}

# ---------------------------------------------------------------------------
# 7) B772 ENGINE by operator (the only base type with >1 engine option).
#    Engine NAME is cosmetic; thrust spread is ~4% (immaterial under P00), so
#    this is a convenience map to avoid the per-tail flag for known operators.
#    Only high-confidence, single-engine-family fleets here; mixed fleets (e.g.
#    BA: GE90 + Trent) are omitted on purpose so they still flag. Extend freely.
# ---------------------------------------------------------------------------
OPERATOR_ENGINE_B772 = {
    "KLM": "GE90-94B",   # all KLM 777-200ER
    "CPA": "Trent 877",  # Cathay 777-200 (RR Trent 800) -> sim Trent 892
    "UAL": "PW4090",     # United 777-200/200ER (PW4000)
    "ANA": "PW4090",     # ANA 777-200 (PW4000)
    "JAL": "PW4090",     # JAL 777-200 (PW4000)
    "AAL": "Trent 892",  # American 777-200ER (RR Trent 800)
    "SIA": "Trent 884",  # Singapore 777-200ER (RR Trent 800) -> sim Trent 892
}

