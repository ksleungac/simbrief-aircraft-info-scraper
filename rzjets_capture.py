"""
rzjets.net structure probe (public site, behind Cloudflare -> needs HEADFUL).
Usage:  python rzjets_capture.py <REG>      e.g. python rzjets_capture.py B-KQD
Passes the Cloudflare JS challenge with a real headful browser, then drives the
search box for a registration and dumps text + HTML to ./rzjets_out so we can
learn the field labels (SELCAL, engines, MSN, delivery) and the URL structure.
Run this to RE-LEARN rzjets layout if it changes.  Set HEADLESS=1 to override.
"""
from playwright.sync_api import sync_playwright
import sys, os, re, time

reg = (sys.argv[1] if len(sys.argv) > 1 else "B-KQD").upper()
OUT = r"C:\simbrief-fleet\rzjets_out"
os.makedirs(OUT, exist_ok=True)
BASE = "https://rzjets.net"
HEADLESS = os.environ.get("HEADLESS", "0") == "1"

def clear_cloudflare(page, timeout=150):
    """Wait until the Cloudflare challenge clears AND real content has loaded.
    rzjets uses Turnstile -> CLICK the 'Verify you are human' checkbox in the
    headful window; this polls up to `timeout`s for you to do it."""
    print(f"  ... if you see a Cloudflare 'Verify you are human' box, CLICK it "
          f"(waiting up to {timeout}s)")
    for _ in range(timeout):
        try:
            t = page.inner_text("body")
        except Exception:
            t = ""
        low = t.lower()
        challenging = ("security verification" in low or "verifying you are" in low
                       or "__cf_chl" in page.url or "just a moment" in low)
        if not challenging and len(t.strip()) > 200:
            return True
        time.sleep(1)
    return False

def dump(name, page):
    txt = page.inner_text("body"); html = page.content()
    with open(os.path.join(OUT, f"{reg}_{name}.txt"), "w", encoding="utf-8") as f:
        f.write("URL: " + page.url + "\n\n" + txt)
    with open(os.path.join(OUT, f"{reg}_{name}.html"), "w", encoding="utf-8") as f:
        f.write(html)
    return txt, html

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), ".rzjets-profile"),
        headless=HEADLESS, no_viewport=True,
        args=["--start-maximized", "--disable-blink-features=AutomationControlled"],
        ignore_default_args=["--enable-automation"])
    ctx.add_init_script(
        "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});")
    page = ctx.pages[0] if ctx.pages else ctx.new_page()

    page.goto(f"{BASE}/aircraft/", wait_until="domcontentloaded", timeout=60000)
    ok = clear_cloudflare(page)
    print("cloudflare cleared:", ok)
    home_txt, home_html = dump("home", page)

    # find search inputs on the page
    inputs = page.eval_on_selector_all(
        "input, select",
        "els => els.map(e => ({name:e.name, id:e.id, type:e.type, ph:e.placeholder}))")
    print("inputs on page:", inputs)
    forms = page.eval_on_selector_all(
        "form", "els => els.map(e => ({action:e.action, method:e.method}))")
    print("forms:", forms)

    # try typing the reg into the most likely search box, submit
    typed = False
    for sel in ["input[name='reg']", "input[name='search']", "input[type='search']",
                "input[type='text']", "input#search", "input#reg"]:
        if page.query_selector(sel):
            try:
                page.fill(sel, reg); page.press(sel, "Enter")
                page.wait_for_load_state("domcontentloaded", timeout=30000)
                clear_cloudflare(page)
                typed = True
                print(f"typed into {sel} -> {page.url}")
                break
            except Exception as e:
                print(f"type {sel} failed: {e}")
    if typed:
        res_txt, res_html = dump("search", page)
        links = re.findall(r'href="([^"]*aircraft[^"]*)"', res_html)
        detail = [l for l in links if re.search(r'(id|parent_id|reg_id)=\d+', l)]
        print("detail-ish links:", detail[:8])
        hit = reg in res_txt or reg.replace("-", "") in res_txt
        print(f"search page: len={len(res_txt)} reg_in_text={hit} "
              f"SELCAL={'SELCAL' in res_txt.upper()} ENGINE={'ENGINE' in res_txt.upper()}")
        if detail:
            link = detail[0]
            if link.startswith("/"): link = BASE + link
            elif not link.startswith("http"): link = BASE + "/aircraft/" + link
            page.goto(link, wait_until="domcontentloaded", timeout=30000)
            clear_cloudflare(page)
            d_txt, _ = dump("detail", page)
            print(f"\n[detail] {page.url}\n--- first 2000 chars ---\n{d_txt[:2000]}")

    # also try direct reg URLs now that the clearance cookie is set
    for label, url in [("reg_param", f"{BASE}/aircraft/?reg={reg}"),
                       ("reg_nodash", f"{BASE}/aircraft/?reg={reg.replace('-','')}")]:
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            clear_cloudflare(page, timeout=20)
            t, h = dump(label, page)
            hit = reg in t or reg.replace("-", "") in t
            print(f"[{label}] {page.url} len={len(t)} reg_in_text={hit} "
                  f"SELCAL={'SELCAL' in t.upper()} ENGINE={'ENGINE' in t.upper()}")
        except Exception as e:
            print(f"[{label}] ERROR {e}")
    ctx.close()
print("\nDumped to", OUT)
