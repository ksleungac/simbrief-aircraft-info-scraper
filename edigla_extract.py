"""
edi-gla automated extractor (reuses the persisted login).
Usage:  python edigla_extract.py <REG> <CALLSIGN> <AIRCRAFT_ICAO>
   e.g. python edigla_extract.py B-HND CPA B772

Strategy:
  1) search remarks = REG/<reg>  (exact tail) -> results table
     fallback: callsign + aircraft only (then newest plan as proxy)
  2) pick the NEWEST plan (max flightplan id) -> most likely modern equip format
  3) open the flight plan, read Aircraft / Equipment / Remarks
  4) open ?operation=explain-equip for the full 10a / 10b breakdown
  5) parse Field-18 remarks: REG/ SEL/ NAV/ PBN/ DAT/ CODE/ COM/ SUR/
Outputs JSON + raw dumps to ./edigla_out for inspection.
"""
from playwright.sync_api import sync_playwright
import sys, os, re, json, urllib.parse

PROFILE = r"C:\simbrief-fleet\.edigla-profile"
OUTDIR  = r"C:\simbrief-fleet\edigla_out"
os.makedirs(OUTDIR, exist_ok=True)
BASE = "https://edi-gla.co.uk"

reg      = (sys.argv[1] if len(sys.argv) > 1 else "B-HND").upper()
callsign = (sys.argv[2] if len(sys.argv) > 2 else "CPA").upper()
ac_icao  = (sys.argv[3] if len(sys.argv) > 3 else "B772").upper()
reg_nodash = reg.replace("-", "")

def search_url(remarks=""):
    p = {
        "Flightplan[callsign]": callsign,
        "Flightplan[aircraft_icao]": ac_icao,
        "Flightplan[remarks]": remarks,
        "Flightplan[search_sort_field]": "fpl_id",
        "Flightplan[search_sort_order]": "3",
    }
    return BASE + "/flightplan/search?" + urllib.parse.urlencode(p)

def grab(html, label):
    m = re.search(r"<label>%s</label>\s*(.*?)(?:</div>|<a )" % re.escape(label), html, re.S)
    if not m:
        return ""
    txt = re.sub(r"<[^>]+>", " ", m.group(1))
    return re.sub(r"\s+", " ", txt).strip()

def parse_field18(remarks):
    out = {}
    for key, val in re.findall(r"([A-Z]{2,5})/(.*?)(?=\s+[A-Z]{2,5}/|$)", remarks, re.S):
        out[key] = re.sub(r"\s+", " ", val).strip()
    return out

result = {"reg": reg, "callsign": callsign, "aircraft_icao": ac_icao}

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(PROFILE, headless=False, no_viewport=True,
                                               args=["--start-maximized"])
    page = ctx.pages[0] if ctx.pages else ctx.new_page()

    # 1) search by REG/, fallback to callsign+type
    used = None
    for remarks in (f"REG/{reg_nodash}", ""):
        page.goto(search_url(remarks), wait_until="domcontentloaded", timeout=30000)
        try: page.wait_for_load_state("networkidle", timeout=6000)
        except Exception: pass
        html = page.content()
        ids = [int(x) for x in re.findall(r"/flightplan/(\d+)", html)]
        ids = sorted(set(ids), reverse=True)
        if ids:
            used = remarks or "(callsign+type only)"
            result["search_used"] = used
            result["match_count"] = len(ids)
            result["fpl_ids_top"] = ids[:10]
            break

    if not used or not ids:
        result["error"] = "no flight plans found"
        with open(os.path.join(OUTDIR, f"{reg}.json"), "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        print(json.dumps(result, indent=2)); ctx.close(); sys.exit(0)

    fid = ids[0]  # newest = highest id
    result["chosen_fpl_id"] = fid

    # 3) flight plan page
    page.goto(f"{BASE}/flightplan/{fid}", wait_until="domcontentloaded", timeout=30000)
    try: page.wait_for_load_state("networkidle", timeout=6000)
    except Exception: pass
    fp_html = page.content()
    with open(os.path.join(OUTDIR, f"{reg}_flightplan.html"), "w", encoding="utf-8") as f:
        f.write(fp_html)
    result["aircraft"]  = grab(fp_html, "Aircraft")
    result["equipment_short"] = grab(fp_html, "Equipment")
    remarks_txt = grab(fp_html, "Remarks")
    result["remarks_raw"] = remarks_txt
    f18 = parse_field18(remarks_txt)
    result["field18"] = f18
    result["SELCAL"] = f18.get("SEL", "")
    result["NAV"]    = f18.get("NAV", "")
    result["PBN"]    = f18.get("PBN", "")
    result["DAT"]    = f18.get("DAT", "")
    result["CODE_hex"] = f18.get("CODE", "")

    # 4) explain-equip (full 10a/10b) -- dump raw for inspection
    page.goto(f"{BASE}/flightplan/{fid}?operation=explain-equip",
              wait_until="domcontentloaded", timeout=30000)
    try: page.wait_for_load_state("networkidle", timeout=6000)
    except Exception: pass
    eq_html = page.content()
    with open(os.path.join(OUTDIR, f"{reg}_equip.html"), "w", encoding="utf-8") as f:
        f.write(eq_html)
    eq_text = re.sub(r"<[^>]+>", " ", eq_html)
    result["equip_explain_text"] = re.sub(r"\s+", " ", eq_text).strip()[:1500]

    ctx.close()

with open(os.path.join(OUTDIR, f"{reg}.json"), "w", encoding="utf-8") as f:
    json.dump(result, f, indent=2, ensure_ascii=False)
print(json.dumps({k: v for k, v in result.items() if k != "equip_explain_text"}, indent=2, ensure_ascii=False))
print("\n--- equip explain (first 600 chars) ---\n", result.get("equip_explain_text", "")[:600])
