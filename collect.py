"""
collect.py <REGISTRATION>  [callsign] [aircraft_icao]
One hardened command: gathers every field I can for a B777 airframe and appends a
row to fleet.json, then rebuilds the workbook. Designed to run WITHOUT supervision:
  - one browser session (persistent edi-gla login) reused for all sources
  - every external step wrapped: on failure it records a flag and carries on
  - it NEVER crashes the run; a partial row is always written with notes
Sources: airport-data.com (hex, operator, type), cabin via curated table +
live seatmaps.com (operator+type configs), edi-gla (SELCAL, equipment 10a/10b,
PBN), static_data (weights, thrust, units, name).
Optional callsign / aircraft_icao args override auto-detection.
"""
import os, sys, re, json, time, subprocess
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import static_data as S

PROFILE = os.path.join(HERE, ".edigla-profile")
FLEET   = os.path.join(HERE, "fleet.json")
HEADLESS = os.environ.get("HEADLESS", "0") == "1"

OPERATOR_ICAO = {
    "cathay":"CPA","nippon":"ANA","japan airlines":"JAL"," jal ":"JAL","united":"UAL",
    "american":"AAL","delta":"DAL","british":"BAW","emirates":"UAE","qatar":"QTR",
    "singapore":"SIA","korean":"KAL","air france":"AFR","klm":"KLM","lufthansa":"DLH",
    "turkish":"THY","etihad":"ETD","saudi":"SVA","air new zealand":"ANZ","eva":"EVA",
    "china airlines":"CAL","china southern":"CSN","china eastern":"CES","air india":"AIC",
    "thai":"THA","malaysia":"MAS","asiana":"AAR","ethiopian":"ETH","garuda":"GIA",
    "philippine":"PAL","kuwait":"KAC","egyptair":"MSR","pakistan":"PIA","swiss":"SWR",
    "air canada":"ACA","aeroflot":"AFL","jin air":"JNA","austrian":"AUA",
}
ICAO_NAME = {
    "CPA":"Cathay Pacific","ANA":"All Nippon Airways","JAL":"Japan Airlines","UAL":"United Airlines",
    "AAL":"American Airlines","DAL":"Delta Air Lines","BAW":"British Airways","UAE":"Emirates",
    "QTR":"Qatar Airways","SIA":"Singapore Airlines","KAL":"Korean Air","AFR":"Air France","KLM":"KLM",
    "DLH":"Lufthansa","THY":"Turkish Airlines","ETD":"Etihad Airways","SVA":"Saudia","ANZ":"Air New Zealand",
    "EVA":"EVA Air","CAL":"China Airlines","CSN":"China Southern","CES":"China Eastern","AIC":"Air India",
    "THA":"Thai Airways","MAS":"Malaysia Airlines","AAR":"Asiana Airlines","ETH":"Ethiopian Airlines",
    "GIA":"Garuda Indonesia","PAL":"Philippine Airlines","KAC":"Kuwait Airways","MSR":"EgyptAir",
    "PIA":"Pakistan Intl","SWR":"Swiss","ACA":"Air Canada","AFL":"Aeroflot","JNA":"Jin Air","AUA":"Austrian",
}

def retry(fn, tries=3, wait=2, label=""):
    for i in range(tries):
        try:
            return fn()
        except Exception as e:
            if i == tries - 1:
                print(f"  ! {label} failed after {tries}: {e}")
                return None
            time.sleep(wait)

def text_of(page, url, timeout=30000):
    page.goto(url, wait_until="domcontentloaded", timeout=timeout)
    try: page.wait_for_load_state("networkidle", timeout=6000)
    except Exception: pass
    return page.inner_text("body"), page.content()

# ---------- source: airport-data.com (hex, operator, type) ----------
def airportdata(page, reg, flags):
    def go():
        txt, html = text_of(page, f"https://airport-data.com/aircraft/{reg}.html")
        out = {}
        m = re.search(r"ICAO24.{0,25}?\b([0-9A-Fa-f]{6})\b", txt, re.S | re.I)
        if not m:
            m = re.search(r"Mode\s*S.{0,40}?\b([0-9A-Fa-f]{6})\b", txt, re.S | re.I)
        out["hex"] = m.group(1).upper() if m else None
        mt = re.search(r"(777[-\s]?\d{2,3}/?(?:ER|LR|F)?)", txt)
        t = mt.group(1).strip() if mt else None
        if not t and re.search(r"777\s*F|freight", txt, re.I):
            t = "777F"
        out["type"] = t
        low = txt.lower(); op = None
        for kw in OPERATOR_ICAO:
            if kw.strip() and kw.strip() in low:
                op = kw.strip(); break
        if not op:
            mo = re.search(r"(?:Airline|Operator|Owner)\s*[:\-]?\s*([A-Z][A-Za-z .&'()/-]{2,40})", txt)
            op = mo.group(1).strip() if mo else None
        out["operator"] = op
        return out
    r = retry(go, label="airport-data")
    if not r:
        flags.append("airport-data unreachable")
        return {}
    if not r.get("hex"): flags.append("hex not found")
    if not r.get("type"): flags.append("type not found on airport-data")
    if not r.get("operator"): flags.append("operator not found on airport-data")
    return r

# ---------- derive base type / variant / ER from type string ----------
def derive(type_str, flags):
    s = (type_str or "").upper()
    if "777F" in s or "777-F" in s or "FREIGHT" in s:
        return "B77F", "777F", False
    if "LR" in s:
        return "B77L", "777-200LR", False
    gen = re.search(r"777-?([23])", s)
    er = "ER" in s
    if gen and gen.group(1) == "3":
        if er: return "B77W", "777-300ER", False
        flags.append("777-300 classic - no SimBrief profile (out of scope)")
        return None, "777-300", False
    # default / generation 2
    if er: return "B772", "777-200ER", True
    return "B772", "777-200", False

def operator_icao(name, flags):
    if not name:
        flags.append("operator unknown - cannot search edi-gla"); return None
    low = " " + name.lower() + " "
    for kw, icao in OPERATOR_ICAO.items():
        if kw in low:
            return icao
    flags.append(f"operator '{name}' not in ICAO map - cannot search edi-gla")
    return None

# ---------- source: cabin layout (curated table -> live seatmaps.com) ----------
# No free source maps a registration to its current cabin, so we resolve by
# operator+type: a curated table first (authoritative, marks 'latest'), then a
# live seatmaps.com scrape. Always default latest, list candidates, flag confirm.
_CLASS_RE = re.compile(
    r"(\d{1,3})\s*(?:x\s*)?"
    r"(First|World\s*Business|Business|Premium\s*Economy|Premium\s*Comfort|Economy|Main\s*Cabin)\b",
    re.I)

def _parse_cabin_text(txt):
    """Extract (F/C/W/Y, count) pairs from page text. Best-effort, conservative."""
    pairs = []
    for n, name in _CLASS_RE.findall(txt):
        k = name.lower()
        if "premium" in k:   code = "W"
        elif "business" in k: code = "C"
        elif "first" in k:    code = "F"
        else:                 code = "Y"      # economy / main cabin
        pairs.append((code, int(n)))
    return pairs

def _fmt_config(pairs):
    """(F/C/W/Y, count) pairs -> ('F8C64W24Y116', 212). Last count wins per class."""
    order = {"F": 0, "C": 1, "W": 2, "Y": 3}
    seen = {}
    for code, n in pairs:
        seen[code] = n
    items = sorted(seen.items(), key=lambda x: order.get(x[0], 9))
    if not items:
        return None, None
    return "".join(f"{c}{n}" for c, n in items), sum(n for _, n in items)

def cabin(page, reg, icao, base, flags, infos):
    if base == "B77F":
        return None, None                       # freighter: no pax cabin
    # 1) curated table (authoritative)
    configs = S.cabin_candidates(icao, base)
    if configs:
        latest = S.pick_latest(configs)
        if len(configs) == 1:                                   # no choice -> info only
            infos.append(f"cabin {latest['code']} ({icao}/{base} single config [{latest['label']}])")
        elif (icao, base) in S.CABIN_AUTO_LATEST:               # full conversion -> auto, info only
            infos.append(f"cabin {latest['code']} ({icao}/{base} auto-latest, forward-valid [{latest['label']}])")
        else:                                                   # holdouts exist -> needs confirm
            alts = "; ".join(f"{c['code']}={c['pax']}({c['label']})" for c in configs)
            flags.append(f"cabin: {len(configs)} {icao}/{base} configs -> defaulted LATEST "
                         f"{latest['code']} [{latest['label']}], CONFIRM tail. candidates: {alts}")
        return latest["code"], latest["pax"]
    # 2) live seatmaps.com (operators not yet curated)
    slug = S.SEATMAPS_SLUG.get(icao)
    tslug = S.SEATMAPS_TYPE.get(base)
    if slug and tslug:
        url = f"https://seatmaps.com/airlines/{slug}/{tslug}/"
        pairs = retry(lambda: _parse_cabin_text(text_of(page, url)[0]), tries=2, label="seatmaps") or []
        codes = [c for c, _ in pairs]
        if pairs and len(codes) == len(set(codes)):     # one clean version
            code, pax = _fmt_config(pairs)
            flags.append(f"cabin: live seatmaps single-config {code} ({icao} not curated) - VERIFY {url}")
            return code, pax
        if pairs:                                        # several versions merged - don't guess
            flags.append(f"cabin: seatmaps has MULTIPLE {icao}/{base} configs - set manually: {url}")
            return None, None
        flags.append(f"cabin: not found ({icao} not curated; seatmaps empty) {url}")
        return None, None
    # 3) no source
    flags.append(f"cabin: no source for {icao or '?'}/{base or '?'} - add to CABIN_CONFIGS")
    return None, None

# ---------- source: edi-gla (SELCAL, equipment, PBN) ----------
def edigla(page, reg, callsign, ac_icao, flags):
    import urllib.parse
    reg_nodash = reg.replace("-", "")
    def search(remarks):
        p = {"Flightplan[callsign]": callsign, "Flightplan[aircraft_icao]": ac_icao,
             "Flightplan[remarks]": remarks, "Flightplan[search_sort_field]": "fpl_id",
             "Flightplan[search_sort_order]": "3"}
        url = "https://edi-gla.co.uk/flightplan/search?" + urllib.parse.urlencode(p)
        _, html = text_of(page, url)
        return html
    out = {"SELCAL": "", "10a": "", "10b": "", "PBN": "", "DAT": "", "fpl_id": None,
           "modern": False, "exact": False}
    try:
        # 1) EXACT tail first: remarks 'contains' REG/<reg> (the reg lives in Field-18 RMK)
        html = retry(lambda: search(f"REG/{reg_nodash}"), tries=2, label="edi-gla REG search") or ""
        if "password" in html.lower() and "/flightplan/" not in html:
            flags.append("edi-gla NOT logged in - session expired"); return out
        ids = sorted({int(x) for x in re.findall(r"/flightplan/(\d+)", html)}, reverse=True)
        out["exact"] = bool(ids)
        if not ids:
            # 2) NO exact-reg plan -> never borrow per-tail SELCAL; only borrow equip/PBN from a sibling
            flags.append("edi-gla: NO exact-reg plan -> SELCAL left blank (per-tail, cannot borrow)")
            html = retry(lambda: search(""), tries=2, label="edi-gla sibling search") or ""
            ids = sorted({int(x) for x in re.findall(r"/flightplan/(\d+)", html)}, reverse=True)
            if not ids:
                flags.append("edi-gla: no sibling plan either"); return out
            flags.append(f"edi-gla: equip/PBN borrowed from newest {callsign}/{ac_icao} sibling "
                         f"fpl{ids[0]} - VERIFY vintage (equipment drifts with airframe age)")
        fid = ids[0]; out["fpl_id"] = fid
        out["search"] = "REG/ exact" if out["exact"] else f"sibling fpl{fid}"
        _, fp = text_of(page, f"https://edi-gla.co.uk/flightplan/{fid}")
        def grab(label):
            m = re.search(r"<label>%s</label>\s*(.*?)(?:</div>|<a )" % label, fp, re.S)
            return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", m.group(1))).strip() if m else ""
        equip = grab("Equipment")
        parts = equip.split("/")
        # equip codes never contain spaces; scrape can inject them at line breaks
        eq10a = re.sub(r"\s+", "", parts[0])
        eq10b = re.sub(r"\s+", "", parts[1]) if len(parts) > 1 else ""
        if eq10a:
            out["10a"], out["10b"], out["modern"] = eq10a, eq10b, True
        else:
            out["10b"] = eq10b
            flags.append(f"edi-gla equip old-format ('{equip}') - SimBrief default for 10a")
        rem = grab("Remarks")
        f18 = dict(re.findall(r"([A-Z]{2,5})/(.*?)(?=\s+[A-Z]{2,5}/|$)", rem, re.S))
        out["PBN"] = (f18.get("PBN") or "").strip()
        out["DAT"] = (f18.get("DAT") or "").strip()
        if not out["PBN"] and f18.get("NAV"):
            out["PBN"] = "NAV/ " + f18["NAV"].strip()
            flags.append("edi-gla: no PBN/, captured NAV/ instead (verify)")
        # SELCAL is PER-TAIL -> only trust it from an exact-reg plan, never from a sibling
        if out["exact"]:
            out["SELCAL"] = (f18.get("SEL") or "").strip()
            if not out["SELCAL"]:
                flags.append("edi-gla: SELCAL not found in exact plan")
    except Exception as e:
        flags.append(f"edi-gla error: {e}")
    return out

LB = S.KG_TO_LB
def conv(kg, units):
    if kg is None: return None
    return round(kg * LB / 100) * 100 if units == "LB" else kg

# ---------- source: rzjets (opt-in cross-check; Turnstile-gated -> headful) ----------
# rzjets has per-tail SELCAL/engine/cn/ln/delivery + registration history. It sits
# behind Cloudflare Turnstile, so it runs HEADFUL reusing .rzjets-profile clearance
# (refresh by running rzjets_capture.py and clicking once). Opt-in via RZJETS=1 so
# default unattended runs stay headless and never hang on the challenge.
def rzjets(reg, flags, infos):
    out_path = os.path.join(HERE, "rzjets_out", reg.upper() + ".json")
    try:
        if os.path.exists(out_path): os.remove(out_path)
    except Exception: pass
    try:
        env = dict(os.environ); env.pop("HEADLESS", None)   # force headful to use clearance
        subprocess.run([sys.executable, os.path.join(HERE, "rzjets_extract.py"), reg],
                       capture_output=True, text=True, env=env, timeout=180)
        data = json.load(open(out_path, encoding="utf-8")) if os.path.exists(out_path) else {}
    except Exception as e:
        flags.append(f"rzjets error: {e}"); return {}
    if data.get("blocked"):
        flags.append(f"rzjets blocked (Turnstile) - refresh: python rzjets_capture.py {reg}")
    elif not data.get("found"):
        infos.append(f"rzjets: no match for {reg}")
    return data

def _deliv_year(dd):                       # "02/19/13" -> "2013"
    if not dd: return ""
    yy = dd[-2:]
    return ("20" if int(yy) < 50 else "19") + yy

def collect_one(page, reg, cs_override=None, ac_override=None):
    """Collect ONE registration on an already-open page. Returns (rec, flags, infos).
    flags = action-needed (-> Status 'Check'); infos = informational only."""
    reg = reg.upper()
    flags, infos = [], []
    rec = {"Registration": reg, "OEW": None, "Max Cargo": None,
           "Fuel Factor": "P00", "Cost Index": "(SB default)"}

    ad = airportdata(page, reg, flags)
    rec["Hex"] = ad.get("hex")
    rec["Operator"] = ad.get("operator")
    base, variant, is_er = derive(ad.get("type"), flags)
    if ac_override:  # explicit base override
        base = ac_override
    rec["Base Type"] = base
    rec["Variant"] = (ad.get("type") or variant or "").replace("/", "")
    units = S.units_for_registration(reg)
    rec["Units"] = units
    icao = cs_override or operator_icao(ad.get("operator"), flags)
    if icao in ICAO_NAME: rec["Operator"] = ICAO_NAME[icao]

    cab, pax = cabin(page, reg, icao, base, flags, infos)
    rec["Max Pax"] = pax
    if icao:
        rec["Airframe Name"] = " ".join(["FF", icao] + (["ER"] if is_er else []) + [cab or "C??Y??"])
    else:
        rec["Airframe Name"] = None

    # weights + thrust from static
    if base in S.WEIGHTS_KG:
        w = S.WEIGHTS_KG[base]
        mtow, mlw, mzfw, fuel = w["MTOW"], w["MLW"], w["MZFW"], w["MaxFuel"]
        if base == "B772" and not is_er:
            mtow, fuel = w["_200_basic"]["MTOW"], w["_200_basic"]["MaxFuel"]
        rec["MTOW"], rec["MLW"] = conv(mtow, units), conv(mlw, units)
        rec["MZFW"], rec["Max Fuel"] = conv(mzfw, units), conv(fuel, units)
        choices = w["engine_choice"]
        if len(choices) == 1:
            real_eng = choices[0]
        else:                                    # B772: resolve via operator map (cosmetic)
            real_eng = S.OPERATOR_ENGINE_B772.get(icao)
        if real_eng:
            ff, thr = S.thrust_for_engine(real_eng)
            rec["Eng (real)"], rec["Eng (sim/FF)"], rec["Thrust lbf"] = real_eng, ff, thr
            if len(choices) > 1:
                infos.append(f"engine {real_eng}->{ff} via operator map ({icao}/B772, cosmetic - verify if needed)")
        else:
            rec["Eng (real)"] = None
            flags.append("B772: engine family per-tail - verify (GE90-94B/PW4090/Trent892)")
    else:
        flags.append("base type unresolved - weights/thrust skipped")

    # edi-gla
    eg = {"SELCAL": "", "10a": "", "10b": "", "PBN": "", "fpl_id": None, "search": None}
    if icao and base:
        eg = edigla(page, reg, icao, base, flags)
    rec["SELCAL"] = eg.get("SELCAL") or ""
    rec["Equip 10a"] = eg.get("10a") or "(SB default)"
    rec["Xpdr 10b"] = eg.get("10b") or "(SB default)"
    rec["PBN"] = eg.get("PBN") or "(SB default)"
    rec["Line#/Deliv"] = ""

    # rzjets cross-check / fallback (opt-in: RZJETS=1; headful, Turnstile-gated)
    if os.environ.get("RZJETS") == "1":
        rz = rzjets(reg, flags, infos)
        if rz.get("found"):
            if not rec["SELCAL"] and rz.get("selcal"):
                rec["SELCAL"] = rz["selcal"]; infos.append(f"SELCAL {rz['selcal']} from rzjets")
            if rz.get("cn"):
                rec["Line#/Deliv"] = f"cn{rz['cn']} ln{rz.get('ln','')} / {_deliv_year(rz.get('delivery'))}".strip()
            if base == "B772" and rz.get("engine") in S.ENGINES:
                ff, thr = S.thrust_for_engine(rz["engine"])
                rec["Eng (real)"], rec["Eng (sim/FF)"], rec["Thrust lbf"] = rz["engine"], ff, thr
                infos.append(f"engine {rz['engine']} confirmed via rzjets")
            if rz.get("current") is False:
                flags.append(f"rzjets: {reg} is a FORMER rego (now {rz.get('current_reg','?')}) - verify you want this tail")

    rec["Status"] = "Ready" if not flags else "Check"
    note = ("airport-data(hex/type); cabin(curated/seatmaps); edi-gla fpl%s(%s); static wts/thrust(%s). "
            % (eg.get("fpl_id"), eg.get("search"), units))
    if flags: note += "FLAGS: " + " | ".join(flags) + " "
    if infos: note += "INFO: " + " | ".join(infos) + " "
    rec["Source/Notes"] = note + "*OEW+Cargo pending"
    return rec, flags, infos

def upsert(rec):
    fleet = []
    if os.path.exists(FLEET):
        try: fleet = json.load(open(FLEET, encoding="utf-8"))
        except Exception: fleet = []
    fleet = [r for r in fleet if r.get("Registration") != rec["Registration"]] + [rec]
    json.dump(fleet, open(FLEET, "w", encoding="utf-8"), indent=2, ensure_ascii=False)

def parse_args(argv):
    """-> (jobs, batch). Single: REG [callsign] [icao]. Batch: --batch REG REG ..."""
    if argv and argv[0] in ("--batch", "-b"):
        return [(r.upper(), None, None) for r in argv[1:]], True
    reg = argv[0].upper()
    cs = argv[1].upper() if len(argv) > 1 else None
    ac = argv[2].upper() if len(argv) > 2 else None
    return [(reg, cs, ac)], False

def main():
    if len(sys.argv) < 2:
        print("usage: python collect.py <REG> [callsign] [aircraft_icao]\n"
              "       python collect.py --batch <REG1> <REG2> ...   (one session, walk away)")
        return
    jobs, batch = parse_args(sys.argv[1:])
    if not jobs:
        print("no registrations given"); return

    results = []
    with sync_playwright() as p:
        try:
            ctx = p.chromium.launch_persistent_context(PROFILE, headless=HEADLESS,
                    no_viewport=True, args=["--start-maximized"])
        except Exception as e:
            print("FATAL: cannot launch browser (profile locked? close other runs):", e); return
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        for reg, cs, ac in jobs:
            try:
                rec, flags, infos = collect_one(page, reg, cs, ac)
            except Exception as e:   # never let one tail kill the batch
                rec = {"Registration": reg.upper(), "Status": "Check",
                       "OEW": None, "Max Cargo": None, "Fuel Factor": "P00",
                       "Cost Index": "(SB default)",
                       "Source/Notes": f"FATAL collect error: {e} *OEW+Cargo pending"}
                flags, infos = [str(e)], []
            upsert(rec)              # write each row immediately (crash-safe)
            results.append((rec, flags, infos))
            print(f"\n=== {reg.upper()} -> {rec.get('Status')} ===")
            print(json.dumps(rec, indent=2, ensure_ascii=False))
        ctx.close()

    r = subprocess.run([sys.executable, os.path.join(HERE, "build_sheet.py")],
                       capture_output=True, text=True)
    print("\n" + (r.stdout.strip() or r.stderr.strip()))
    if batch or len(results) > 1:
        print("\n=== batch summary ===")
        for rec, flags, infos in results:
            tag = "CLEAN" if not flags else f"{len(flags)} flag(s)"
            print(f"  {rec['Registration']:8} {str(rec.get('Status')):6} {tag}")

if __name__ == "__main__":
    main()
