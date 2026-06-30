"""
rzjets.net per-registration extractor (reuses the Cloudflare clearance in
.rzjets-profile). Cross-checks / fills SELCAL, engine, cn/ln, delivery, and
flags when a reg is a FORMER rego (airframe re-registered elsewhere).

Usage:  python rzjets_extract.py <REG>            -> prints JSON, writes rzjets_out/<reg>.json
        HEADLESS=1 python rzjets_extract.py <REG>  -> headless (needs a valid clearance cookie)

rzjets is behind Cloudflare Turnstile. If clearance has expired, run
`python rzjets_capture.py <REG>` once and click the box to refresh .rzjets-profile.

Search form: POST /aircraft/ field `registry`. Result links a rego id in BOTH
?reg=<id> and ?sel=<id>, so SELCAL maps unambiguously to the exact tail.
"""
from playwright.sync_api import sync_playwright
import sys, os, re, json, time

HERE = os.path.dirname(os.path.abspath(__file__))
PROFILE = os.path.join(HERE, ".rzjets-profile")
OUTDIR = os.path.join(HERE, "rzjets_out")
HEADLESS = os.environ.get("HEADLESS", "0") == "1"
BASE = "https://rzjets.net"

def clear_cloudflare(page, timeout=30):
    for _ in range(timeout):
        try: t = page.inner_text("body")
        except Exception: t = ""
        low = t.lower()
        busy = ("security verification" in low or "verifying you are" in low
                or "__cf_chl" in page.url or "just a moment" in low)
        if not busy and len(t.strip()) > 200:
            return True
        time.sleep(1)
    return False

def parse_rzjets(html, reg):
    reg_u = reg.upper()
    out = {"reg": reg_u, "found": False, "current": None, "current_reg": "",
           "selcal": "", "engine": "", "cn": "", "ln": "", "delivery": ""}
    # the searched rego's link -> capture its id + whether its <td> is current/historic
    m = re.search(r'<td class="(current\w*|historic)"[^>]*>\s*(?:<img[^>]*>)?\s*'
                  r'<a href="[^"]*\?reg=(\d+)">' + re.escape(reg_u) + r'</a>', html)
    if not m:
        return out
    out["found"] = True
    cls, rid = m.group(1), m.group(2)
    out["current"] = cls.startswith("current")
    ms = re.search(r'\?sel=' + rid + r'">([A-Z]{2}-?[A-Z]{2})</a>', html)
    if ms:
        out["selcal"] = ms.group(1).replace("-", "")
    md = re.search(r'\?reg=' + rid + r'">' + re.escape(reg_u) + r'</a>.*?\bdd (\d\d/\d\d/\d\d)', html, re.S)
    if md:
        out["delivery"] = md.group(1)
    mc = re.search(r'<td class="current"[^>]*>(\d{4,6})</td>', html)
    if mc: out["cn"] = mc.group(1)
    ml = re.search(r'<td class="currentnw">(\d{2,5})</td>', html)
    if ml: out["ln"] = ml.group(1)
    me = re.search(r'(GE90-\d{2,3}B\d?|Trent \d{3}|PW40\d\d)', html)
    if me: out["engine"] = me.group(1)
    if out["current"] is False:
        mr = re.search(r'<td class="current\w*"[^>]*>\s*(?:<img[^>]*>)?\s*'
                       r'<a href="[^"]*\?reg=\d+">([A-Z0-9-]+)</a>', html)
        if mr: out["current_reg"] = mr.group(1)
    return out

def lookup(reg):
    os.makedirs(OUTDIR, exist_ok=True)
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            PROFILE, headless=HEADLESS, no_viewport=True,
            args=["--start-maximized", "--disable-blink-features=AutomationControlled"],
            ignore_default_args=["--enable-automation"])
        ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined});")
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            page.goto(f"{BASE}/aircraft/", wait_until="domcontentloaded", timeout=60000)
            if not clear_cloudflare(page):
                ctx.close()
                return {"reg": reg.upper(), "found": False, "blocked": True}
            page.fill("#registry", reg.upper())
            page.click("#submitB")
            page.wait_for_load_state("domcontentloaded", timeout=30000)
            clear_cloudflare(page, 20)
            html = page.content()
        finally:
            try: ctx.close()
            except Exception: pass
    res = parse_rzjets(html, reg)
    res["blocked"] = False
    return res

if __name__ == "__main__":
    reg = (sys.argv[1] if len(sys.argv) > 1 else "B-KQD").upper()
    res = lookup(reg)
    os.makedirs(OUTDIR, exist_ok=True)
    with open(os.path.join(OUTDIR, f"{reg}.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, indent=2)
    print(json.dumps(res, indent=2))
