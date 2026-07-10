"""
CI estimator - LOCAL visualization (never published; local html only, per CLAUDE.md).

Reads cruise samples (+ route cache) and writes a self-contained ci_viz.html you open locally:
    file://<path>       or       python -m http.server 8000  ->  http://localhost:8000/ci_viz.html

    python ci_viz.py                          # ci_samples.jsonl + route_cache.json -> ci_viz.html
    python ci_viz.py --in x.jsonl --out y.html

The chart: one point per flight per FL, IAS vs flight level, colored+shaped by haul tier
(dom/reg/intl/?). Dashed line = median IAS per FL. Operator filter, tier toggles, table view.
Template lives in ci_viz_template.html (edit there); data is injected at the __DATA__ marker.
"""
import argparse
import json
import os
from statistics import median
from ci_collect import haul_tier

DEFAULT_TEMPLATE = "ci_viz_template.html"


def build_points(samples, cache):
    """One point per (hex, fl) = median IAS, tagged op/type/haul-tier."""
    pts = {}
    for s in samples:
        r = cache.get(s.get("flight"))
        tier = haul_tier(r["oc"], r["dc"]) if r else "?"
        k = (s["hex"], s["fl"])
        d = pts.setdefault(k, {"op": s["op"], "t": s.get("t"), "tier": tier,
                               "fl": s["fl"], "ias": []})
        d["ias"].append(s["ias"])
    return [{"op": v["op"], "t": v["t"], "tier": v["tier"], "fl": v["fl"],
             "ias": round(median(v["ias"]))} for v in pts.values()]


def main():
    ap = argparse.ArgumentParser(description="render cruise IAS samples to a local html chart")
    ap.add_argument("--in", dest="in_", default="ci_samples.jsonl", help="samples file")
    ap.add_argument("--cache", default="route_cache.json", help="route cache (optional)")
    ap.add_argument("--out", default="ci_viz.html", help="output html")
    ap.add_argument("--template", default=DEFAULT_TEMPLATE, help="html template with __DATA__ marker")
    a = ap.parse_args()

    here = os.path.dirname(os.path.abspath(__file__))
    try:
        samples = [json.loads(l) for l in open(a.in_, encoding="utf-8") if l.strip()]
    except FileNotFoundError:
        print(f"no samples: {a.in_} (run `python ci_collect.py collect` first)")
        return
    if not samples:
        print(f"no samples in {a.in_}")
        return
    try:
        cache = json.load(open(a.cache, encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        cache = {}

    tpl_path = a.template if os.path.isabs(a.template) else os.path.join(here, a.template)
    tpl = open(tpl_path, encoding="utf-8").read()
    pts = build_points(samples, cache)
    open(a.out, "w", encoding="utf-8").write(tpl.replace("__DATA__", json.dumps(pts)))

    outabs = os.path.abspath(a.out).replace(os.sep, "/")
    print(f"wrote {len(pts)} flight-points -> {a.out}")
    print(f"open:  file:///{outabs}")
    print(f"  or:  python -m http.server 8000   then   http://localhost:8000/{os.path.basename(a.out)}")


if __name__ == "__main__":
    main()
