"""
CI estimator - DATA COLLECTION (observation side).

Polls airplanes.live for airborne 777s, keeps only clean cruise samples that carry a
broadcast IAS, and accumulates them. `enrich` resolves each flight's route (callsign ->
origin/destination -> countries) into a persistent cache. `report` turns the pile into
tuning targets, optionally split by haul tier:

    OPERATOR TYPE [TIER] FLxxx  ->  IAS median (p25-p75)  n=<distinct flights>

You match one of these in the sim (same FL, comparable weight/route) and tune the FMC
Cost Index until the sim's cruise IAS lands in the range. The sim's FMC is the CI->IAS
table; this tool just hands you the real-world number to aim at. See docs/ci-estimator.md.

Why IAS (not GS, not report-Mach): IAS is the aircraft's own wind-clean air-data value.
Groundspeed is TAS +/- wind; a report's Mach is usually GS-derived so it carries wind too.

We deliberately do NOT collect or infer weight - it's unknown even on a fixed route
(payload varies). Route is kept only for a COARSE haul tier (domestic/regional/intl);
weight reconciliation is left to the user's heuristics.

Usage:
    python ci_collect.py collect                       # all 777 types, poll 60 min
    python ci_collect.py collect --operator CPA        # only Cathay callsigns
    python ci_collect.py collect --minutes 0           # run until Ctrl-C
    python ci_collect.py enrich                         # resolve routes -> route_cache.json
    python ci_collect.py report                         # tuning targets (op x type x FL)
    python ci_collect.py report --haul                  # split by domestic/regional/intl
    python ci_collect.py report --operator CPA --type B77W

Stdlib only (urllib). Hardened: a failed poll / route lookup is logged and skipped, never fatal.
"""
import argparse
import json
import sys
import time
import urllib.request
import urllib.error
from collections import defaultdict
from statistics import median

API = "https://api.airplanes.live/v2/type/"
TYPES_777 = ["B77W", "B772", "B77L", "B77F"]
UA = "simbrief-fleet-ci-collect/1.0 (github.com/ksleungac/simbrief-aircraft-info-scraper)"

# cruise filter
MIN_ALT = 29000          # >= FL290
MAX_ROC = 300            # |barometric rate| < 300 fpm  -> level flight, excludes step climbs
MIN_IAS = 200            # sanity floor: no 777 cruises below ~250 kt IAS at >=FL290; drops
                         # bad Mode-S reads / climbing tails with absent baro_rate (e.g. 174 kt)
DEFAULT_OUT = "ci_samples.jsonl"
DEFAULT_CACHE = "route_cache.json"

# ISO-3166 alpha-2 -> continent, aviation-relevant subset. Straddlers (TR, RU) placed
# pragmatically; the tier is coarse and meant to be adjusted by heuristics. Unknown -> intl.
_CONTINENT = {}
for _cont, _codes in {
    "AS": "JP CN KR HK MO TW TH SG MY ID PH VN KH LA MM BD LK IN PK NP BT MV "
          "AE QA SA KW BH OM YE JO LB IL IR IQ SY AZ GE AM KZ UZ TM KG TJ MN BN TL",
    "EU": "GB IE FR DE NL BE LU CH AT ES PT IT GR MT CY SE NO DK FI IS PL CZ SK HU "
          "RO BG HR SI RS BA ME MK AL EE LV LT UA BY MD RU TR",
    "NA": "US CA MX GT BZ SV HN NI CR PA CU DO HT JM BS TT BB PR",
    "SA": "BR AR CL PE CO EC UY PY BO VE GY SR",
    "AF": "ZA EG ET KE NG MA DZ TN LY SD GH CI SN CM AO MZ TZ UG ZW ZM RW MU SC DJ MG",
    "OC": "AU NZ FJ PG NC PF WS TO VU GU",
}.items():
    for _c in _codes.split():
        _CONTINENT[_c] = _cont


def _get(url):
    """GET json; return dict or None on any failure (never raises)."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError, OSError) as e:
        print(f"  ! poll failed: {e}", file=sys.stderr)
        return None


def _get_text(url):
    """GET; return (status, text) or (None, '') on failure (never raises)."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except (urllib.error.URLError, OSError):
        return None, ""


def _cruise_sample(ac, operator_filter):
    """Return a compact sample dict if ac is a clean cruise 777 with IAS, else None."""
    ias = ac.get("ias")
    alt = ac.get("alt_baro")
    if ias is None or not isinstance(alt, (int, float)):   # alt can be "ground"
        return None
    if alt < MIN_ALT:
        return None
    if ias < MIN_IAS:                                      # sanity floor, drops bad reads
        return None
    roc = ac.get("baro_rate")
    if roc is not None and abs(roc) >= MAX_ROC:            # accept if roc absent
        return None
    flight = (ac.get("flight") or "").strip()
    op = flight[:3].upper() if len(flight) >= 3 and flight[:3].isalpha() else "???"
    if operator_filter and op != operator_filter:
        return None
    return {
        "op": op,
        "flight": flight,
        "hex": ac.get("hex"),
        "r": ac.get("r"),
        "t": ac.get("t"),
        "fl": int(round(alt / 1000.0) * 10),              # nearest 1000 ft -> FLxxx
        "ias": ias,
        "gs": ac.get("gs"),
        "mach": ac.get("mach"),
        "lat": ac.get("lat"),
        "lon": ac.get("lon"),
    }


def collect(args):
    types = [args.type] if args.type else TYPES_777
    url = API + ",".join(types)
    opf = args.operator.upper() if args.operator else None
    deadline = time.time() + args.minutes * 60 if args.minutes else None
    seen = set()          # (hex, fl, minute) -> dedupe near-duplicate consecutive polls
    written = 0
    print(f"collecting {','.join(types)}"
          + (f" op={opf}" if opf else "")
          + f" every {args.interval}s"
          + (f" for {args.minutes} min" if args.minutes else " until Ctrl-C")
          + f" -> {args.out}")
    try:
        with open(args.out, "a", encoding="utf-8") as fh:
            while True:
                data = _get(url)
                acs = (data or {}).get("ac") or (data or {}).get("aircraft") or []
                now = int((data or {}).get("now", time.time() * 1000))
                fresh = 0
                for ac in acs:
                    s = _cruise_sample(ac, opf)
                    if not s:
                        continue
                    key = (s["hex"], s["fl"], now // 60000)   # one per hex/FL/minute
                    if key in seen:
                        continue
                    seen.add(key)
                    s["t_ms"] = now
                    fh.write(json.dumps(s) + "\n")
                    fresh += 1
                fh.flush()
                written += fresh
                print(f"  {time.strftime('%H:%M:%S')}  seen {len(acs)} 777s, "
                      f"+{fresh} cruise samples (total {written})")
                if deadline and time.time() >= deadline:
                    break
                time.sleep(max(1, args.interval))
    except KeyboardInterrupt:
        print("\nstopped.")
    print(f"wrote {written} samples to {args.out}")


def _hexdb_route(cs):
    """callsign -> (orig_icao, dest_icao) or None."""
    st, body = _get_text(f"https://hexdb.io/api/v1/route/icao/{cs}")
    if st != 200 or not body:
        return None
    try:
        route = (json.loads(body).get("route") or "").strip()
    except ValueError:
        return None
    legs = [p.upper() for p in route.replace(" ", "").split("-") if len(p) == 4 and p.isalpha()]
    return (legs[0], legs[-1]) if len(legs) >= 2 else None


def _hexdb_country(icao, cache):
    """ICAO airport -> ISO2 country code (cached in dict), or None."""
    if icao in cache:
        return cache[icao]
    st, body = _get_text(f"https://hexdb.io/api/v1/airport/icao/{icao}")
    cc = None
    if st == 200 and body:
        try:
            cc = json.loads(body).get("country_code")
        except ValueError:
            cc = None
    cache[icao] = cc
    return cc


def enrich(args):
    """Resolve unique callsigns in the samples file to routes/countries -> cache json."""
    try:
        rows = [json.loads(l) for l in open(args.in_, encoding="utf-8") if l.strip()]
    except FileNotFoundError:
        print(f"no samples file: {args.in_} (run `collect` first)")
        return
    try:
        cache = json.load(open(args.cache, encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        cache = {}
    ap = {}   # in-run airport -> country cache
    callsigns = sorted({s["flight"] for s in rows if s.get("flight")})
    todo = [c for c in callsigns if c not in cache]      # only unresolved (successes are sticky)
    print(f"{len(callsigns)} unique callsigns, {len(todo)} to resolve...")
    resolved = 0
    for i, cs in enumerate(todo, 1):
        route = _hexdb_route(cs)
        if route:
            orig, dest = route
            cache[cs] = {"orig": orig, "dest": dest,
                         "oc": _hexdb_country(orig, ap), "dc": _hexdb_country(dest, ap)}
            resolved += 1
        if i % 25 == 0:
            print(f"  {i}/{len(todo)} ({resolved} resolved)")
        time.sleep(0.05)                                 # be polite to hexdb
    json.dump(cache, open(args.cache, "w", encoding="utf-8"), indent=0)
    print(f"resolved {resolved}/{len(todo)} new; cache now {len(cache)} callsigns -> {args.cache}")


def haul_tier(oc, dc):
    """Coarse tier from origin/dest ISO2 countries."""
    if not oc or not dc:
        return "intl"
    if oc == dc:
        return "dom"
    if _CONTINENT.get(oc) and _CONTINENT.get(oc) == _CONTINENT.get(dc):
        return "reg"
    return "intl"


_TIER_ORDER = {"dom": 0, "reg": 1, "intl": 2, "?": 3}


def report(args):
    try:
        rows = [json.loads(l) for l in open(args.in_, encoding="utf-8") if l.strip()]
    except FileNotFoundError:
        print(f"no samples file: {args.in_} (run `collect` first)")
        return
    cache = {}
    if args.haul:
        try:
            cache = json.load(open(args.cache, encoding="utf-8"))
        except (FileNotFoundError, ValueError):
            print(f"no route cache: {args.cache} (run `enrich` first for --haul)")
            return
    opf = args.operator.upper() if args.operator else None
    tyf = args.type.upper() if args.type else None
    # group key -> hex -> [ias...]  so one long flight = one data point
    g = defaultdict(lambda: defaultdict(list))
    for s in rows:
        if opf and s["op"] != opf:
            continue
        if tyf and (s.get("t") or "").upper() != tyf:
            continue
        t = s.get("t") or "?"
        if args.haul:
            r = cache.get(s.get("flight"))
            tier = haul_tier(r["oc"], r["dc"]) if r else "?"
            key = (s["op"], t, tier, s["fl"])
        else:
            key = (s["op"], t, s["fl"])
        g[key][s["hex"]].append(s["ias"])
    if not g:
        print("no matching samples.")
        return
    if args.haul:
        print(f"{'OP':4} {'TYPE':5} {'TIER':5} {'FL':>5}  {'IAS':>5}  {'range':>11}  flights")
        print("-" * 52)
        keyfn = lambda k: (k[0], k[1], _TIER_ORDER.get(k[2], 9), k[3])
    else:
        print(f"{'OP':4} {'TYPE':5} {'FL':>5}  {'IAS':>5}  {'range':>11}  flights")
        print("-" * 46)
        keyfn = lambda k: (k[0], k[1], k[2])
    for key in sorted(g, key=keyfn):
        per_flight = sorted(median(v) for v in g[key].values())
        n = len(per_flight)
        med = median(per_flight)
        lo, hi = per_flight[0], per_flight[-1]
        if n >= 4:
            q = (n - 1) / 4.0
            lo, hi = per_flight[int(q)], per_flight[int(3 * q)]
        rng = "%.0f-%.0f" % (lo, hi)
        if args.haul:
            op, t, tier, fl = key
            print(f"{op:4} {t:5} {tier:5} {('FL%d' % fl):>5}  {med:5.0f}  {rng:>11}  n={n}")
        else:
            op, t, fl = key
            print(f"{op:4} {t:5} {('FL%d' % fl):>5}  {med:5.0f}  {rng:>11}  n={n}")


def main():
    p = argparse.ArgumentParser(description="collect real-world 777 cruise IAS as CI tuning targets")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("collect", help="poll airplanes.live and accumulate cruise IAS samples")
    c.add_argument("--operator", help="ICAO airline code filter, e.g. CPA")
    c.add_argument("--type", help="single ICAO type, e.g. B77W (default: all 777 types)")
    c.add_argument("--interval", type=int, default=60, help="seconds between polls (min 1)")
    c.add_argument("--minutes", type=int, default=60, help="run duration; 0 = until Ctrl-C")
    c.add_argument("--out", default=DEFAULT_OUT, help=f"append samples here ({DEFAULT_OUT})")
    c.set_defaults(func=collect)

    e = sub.add_parser("enrich", help="resolve callsign -> route -> countries into a cache")
    e.add_argument("--in", dest="in_", default=DEFAULT_OUT, help=f"samples file ({DEFAULT_OUT})")
    e.add_argument("--cache", default=DEFAULT_CACHE, help=f"route cache file ({DEFAULT_CACHE})")
    e.set_defaults(func=enrich)

    r = sub.add_parser("report", help="print IAS tuning targets from accumulated samples")
    r.add_argument("--operator", help="filter to one ICAO airline code")
    r.add_argument("--type", help="filter to one ICAO type")
    r.add_argument("--haul", action="store_true", help="split by domestic/regional/intl (needs enrich)")
    r.add_argument("--in", dest="in_", default=DEFAULT_OUT, help=f"samples file ({DEFAULT_OUT})")
    r.add_argument("--cache", default=DEFAULT_CACHE, help=f"route cache file ({DEFAULT_CACHE})")
    r.set_defaults(func=report)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
