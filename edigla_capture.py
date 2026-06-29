"""
edi-gla structure-learning capture (non-headless, persistent login).
You log in by hand once; the password never touches this script (it persists in the
profile dir). As you browse (log in -> open the flight-plan / search area), each new
page state is saved as HTML + screenshot to ./edigla_capture so I can read the layout
and then write the fully automated search + vintage-match + 10a/10b/PBN extractor.
"""
from playwright.sync_api import sync_playwright
import time, os, hashlib

PROFILE = r"C:\simbrief-fleet\.edigla-profile"
OUT     = r"C:\simbrief-fleet\edigla_capture"
os.makedirs(OUT, exist_ok=True)
RUN_SECONDS = 600

def snap(pg, n):
    base = os.path.join(OUT, f"page_{n:02d}")
    try:
        with open(base + ".html", "w", encoding="utf-8") as f:
            f.write(pg.content())
    except Exception as e:
        print("html err", e)
    try:
        pg.screenshot(path=base + ".png", full_page=True)
    except Exception:
        try: pg.screenshot(path=base + ".png")
        except Exception as e: print("png err", e)

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        PROFILE, headless=False, no_viewport=True, args=["--start-maximized"]
    )
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    try:
        page.goto("https://edi-gla.co.uk/", wait_until="domcontentloaded", timeout=30000)
    except Exception as e:
        print("initial goto:", e)

    print("=== Browser open. Log in, then open the flight-plan / search area. ===")
    seen = set()        # (url, content-hash) pairs already saved
    n = 0
    deadline = time.time() + RUN_SECONDS
    while time.time() < deadline:
        for pg in list(ctx.pages):
            try:
                url = pg.url
                if not url or url.startswith("about:"):
                    continue
                body = pg.content()
            except Exception:
                continue
            key = (url, hashlib.md5(body.encode("utf-8", "ignore")).hexdigest())
            if key in seen:
                continue
            seen.add(key)
            n += 1
            try: pg.wait_for_load_state("networkidle", timeout=4000)
            except Exception: pass
            snap(pg, n)
            print(f"[{n}] {url}")
        time.sleep(3)

    print("=== Capture window ended. Session saved. ===")
    ctx.close()
