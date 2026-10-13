"""Measures a page against the design figures in controls/design-figures.json.

ONE standard only: the distance between the letters (ink to ink by default), never box figures.
- Waits for fonts to finish loading, then measures TWICE; if the two readings differ the result is rejected.
- A figure with no selector yet is reported NOT CHECKED. It is never reported as passing.

Usage: python3 tools/measure_spacing.py <page.html or URL> [--viewport desktop|phone] [--json]
"""
import argparse
import io
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VIEWPORTS = {"desktop": (1280, 900), "phone": (390, 844)}

JS_ELEMENTS = """
([sel]) => Array.from(document.querySelectorAll(sel)).map((el, i) => {
  const r = el.getBoundingClientRect();
  return {i, x: r.left + scrollX, y: r.top + scrollY, w: r.width, h: r.height,
          nextMatches: null, text: (el.innerText || '').slice(0, 40)};
})
"""

JS_PAIRS = """
([above, below]) => {
  const out = [];
  for (const a of document.querySelectorAll(above)) {
    const b = a.nextElementSibling;
    if (b && b.matches(below)) {
      const ra = a.getBoundingClientRect(), rb = b.getBoundingClientRect();
      out.push({a: {x: ra.left + scrollX, y: ra.top + scrollY, w: ra.width, h: ra.height, t: (a.innerText||'').slice(0,30)},
                b: {x: rb.left + scrollX, y: rb.top + scrollY, w: rb.width, h: rb.height, t: (b.innerText||'').slice(0,30)}});
    }
  }
  return out;
}
"""

def ink_rows(img, box, bg_tol=24):
    """Return (first_ink_y, last_ink_y) in page coordinates for the region, or None if there is no ink."""
    import numpy as np
    x, y, w, h = [int(round(v)) for v in box]
    x0, y0 = max(x, 0), max(y, 0)
    x1, y1 = min(x + w, img.width), min(y + h, img.height)
    if x1 <= x0 or y1 <= y0:
        return None
    region = np.asarray(img.crop((x0, y0, x1, y1)).convert("RGB")).astype(int)
    # background = most common colour in the region
    flat = region.reshape(-1, 3)
    vals, counts = np.unique(flat, axis=0, return_counts=True)
    bg = vals[counts.argmax()]
    diff = np.abs(region - bg).sum(axis=2)
    rows = np.where((diff > bg_tol).any(axis=1))[0]
    if rows.size == 0:
        return None
    return y0 + int(rows[0]), y0 + int(rows[-1])


def measure_once(page, figures, viewport):
    from PIL import Image
    png = page.screenshot(full_page=True)
    img = Image.open(io.BytesIO(png))
    scale = img.width / page.evaluate("document.documentElement.scrollWidth") if page.evaluate("document.documentElement.scrollWidth") else 1
    results = {}
    for f in figures:
        fid = f["id"]
        if f.get("viewport", "desktop") != viewport:
            continue
        if f.get("status") != "mapped":
            results[fid] = {"state": "NOT CHECKED", "why": "no page selector has been mapped for this figure yet"}
            continue
        if f["kind"] == "width":
            els = page.evaluate(JS_ELEMENTS, [f["selector"]])
            if not els:
                results[fid] = {"state": "NOT CHECKED", "why": "nothing on the page matched the selector"}
                continue
            results[fid] = {"values": [round(e["w"], 1) for e in els]}
        elif f["kind"] == "gap":
            pairs = page.evaluate(JS_PAIRS, [f["above"], f["below"]])
            if not pairs:
                results[fid] = {"state": "NOT CHECKED", "why": "no matching pairs on this page"}
                continue
            vals = []
            for p in pairs:
                a = ink_rows(img, [v * scale for v in (p["a"]["x"], p["a"]["y"], p["a"]["w"], p["a"]["h"])])
                b = ink_rows(img, [v * scale for v in (p["b"]["x"], p["b"]["y"], p["b"]["w"], p["b"]["h"])])
                if a is None or b is None:
                    vals.append(None)
                else:
                    vals.append(round((b[0] - a[1] - 1) / scale, 1))
            results[fid] = {"values": vals, "pairs": [(p["a"]["t"], p["b"]["t"]) for p in pairs]}
    return results


def run(target, viewport="desktop", figures_path=None):
    from playwright.sync_api import sync_playwright
    figures = json.loads(Path(figures_path or ROOT / "controls" / "design-figures.json").read_text(encoding="utf-8"))["figures"]
    url = target if "://" in target else Path(target).resolve().as_uri()
    w, h = VIEWPORTS[viewport]
    with sync_playwright() as pw:
        kw = {}
        exe = os.environ.get("CHROMIUM_PATH")
        if exe:
            kw["executable_path"] = exe
        browser = pw.chromium.launch(**kw)
        page = browser.new_page(viewport={"width": w, "height": h}, device_scale_factor=1)
        page.goto(url, wait_until="networkidle")
        page.evaluate("document.fonts.ready")
        if page.evaluate("document.fonts.status") != "loaded":
            browser.close()
            return {"error": "fonts had not finished loading, so no measurement was taken"}
        first = measure_once(page, figures, viewport)
        page.wait_for_timeout(300)
        second = measure_once(page, figures, viewport)
        browser.close()
    report = []
    for f in figures:
        fid = f["id"]
        if fid not in first:
            continue
        a, b = first[fid], second[fid]
        row = {"id": fid, "what": f["text"], "expected": f.get("expected"), "tolerance": f.get("tolerance", 0)}
        if a.get("state") == "NOT CHECKED":
            row.update(state="NOT CHECKED", why=a["why"])
        elif a["values"] != b["values"]:
            row.update(state="REJECTED", why=f"two readings of the same page disagreed: {a['values']} then {b['values']}")
        else:
            vals = a["values"]
            row["values"] = vals
            if any(v is None for v in vals):
                row.update(state="NOT CHECKED", why="no letters found in one of the two blocks")
            else:
                bad = [v for v in vals if abs(v - f["expected"]) > row["tolerance"]]
                row.update(state="FAIL" if bad else "PASS", off=bad[:5])
        report.append(row)
    return {"viewport": viewport, "standard": "letters to letters (ink to ink)", "figures": report}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("page")
    ap.add_argument("--viewport", default="desktop", choices=list(VIEWPORTS))
    ap.add_argument("--figures")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    res = run(a.page, a.viewport, a.figures)
    if a.json:
        print(json.dumps(res, indent=1))
    else:
        if "error" in res:
            print("NO MEASUREMENT: " + res["error"])
        else:
            print(f"Measured {a.page} ({res['viewport']}) - {res['standard']}")
            for r in res["figures"]:
                extra = r.get("why") or ("measured " + str(r.get("values")) + ", wanted " + str(r["expected"]))
                print(f"  figure {r['id']:>3}  {r['state']:<11} {r['what']} - {extra}")
    bad = "error" in res or any(r["state"] in ("FAIL", "REJECTED") for r in res.get("figures", []))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
