"""Measures a page against the design figures in controls/design-figures.json.

ONE standard only: the distance between the letters, never box figures.
Two ways of reading "letters to letters" exist; the owner chose the first (config measure_mode):
- baseline_to_capheight: from the line the letters sit on (baseline of the LAST line of the upper block) to the top
  of the capitals (cap height) of the FIRST line of the lower block. Tails of g, y, p are ignored. Read from the font
  itself, so it needs the real fonts loaded.
- ink_to_ink: from the lowest painted pixel above to the highest painted pixel below (kept for comparison).
A picture, line or table has no letters; its edge is used.
- Waits for fonts to finish loading, then measures TWICE; if the two readings differ the result is rejected.
- If the page's required fonts (design-figures.json "required_fonts") are not loaded, no measurement is taken.
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


JS_PAIRS_BASELINE = """
([above, below, boxSel]) => {
  const capCache = {};
  const capH = (s) => {
    const k = s.fontFamily + s.fontSize + s.fontWeight + s.fontStyle;
    if (capCache[k] !== undefined) return capCache[k];
    const c = document.createElement('canvas').getContext('2d');
    c.font = `${s.fontStyle} ${s.fontWeight} ${s.fontSize} ${s.fontFamily}`;
    return capCache[k] = c.measureText('H').actualBoundingBoxAscent;
  };
  const leaf = (el, last) => {
    const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT, {acceptNode: n => n.textContent.trim() ? 1 : 3});
    let n = null, x;
    while ((x = w.nextNode())) { n = x; if (!last) break; }
    return n && n.parentElement;
  };
  const baseline = (el, last) => {
    const lf = leaf(el, last);
    if (!lf) return null;
    const probe = document.createElement('span');
    probe.style.cssText = 'display:inline-block;width:0;height:0;vertical-align:baseline;padding:0;margin:0;border:0';
    if (last) lf.appendChild(probe); else lf.insertBefore(probe, lf.firstChild);
    const y = probe.getBoundingClientRect().bottom + scrollY;
    probe.remove();
    return {y, s: getComputedStyle(lf)};
  };
  const edges = (el) => {
    const r = el.getBoundingClientRect();
    const top = r.top + scrollY, bot = r.bottom + scrollY;
    const isBox = el.matches(boxSel) || !el.textContent.trim();
    if (isBox) return {top, bot, kind: 'box'};
    const f = baseline(el, false), l = baseline(el, true);
    return {top: f.y - capH(f.s), bot: l.y, kind: 'letters'};
  };
  const out = [];
  for (const a of document.querySelectorAll(above)) {
    const b = a.nextElementSibling;
    if (b && b.matches(below)) {
      const ea = edges(a), eb = edges(b);
      out.push({gap: eb.top - ea.bot, kinds: [ea.kind, eb.kind],
                a: {t: (a.innerText || '').slice(0, 30)}, b: {t: (b.innerText || '').slice(0, 30)}});
    }
  }
  return out;
}
"""

DEFAULT_BOX_SELECTOR = "figure, img, table, hr, svg, video, picture"


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


def measure_once(page, figures, viewport, mode="baseline_to_capheight"):
    from PIL import Image
    img, scale = None, 1
    if mode == "ink_to_ink":
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
        elif f["kind"] == "gap" and mode == "baseline_to_capheight":
            pairs = page.evaluate(JS_PAIRS_BASELINE, [f["above"], f["below"], f.get("box_selector", DEFAULT_BOX_SELECTOR)])
            if not pairs:
                results[fid] = {"state": "NOT CHECKED", "why": "no matching pairs on this page"}
                continue
            results[fid] = {"values": [round(p["gap"], 1) for p in pairs], "pairs": [(p["a"]["t"], p["b"]["t"]) for p in pairs]}
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


def load_mode():
    try:
        return json.loads((ROOT / "controls" / "config.json").read_text(encoding="utf-8")).get("measure_mode", "baseline_to_capheight")
    except Exception:
        return "baseline_to_capheight"


def load_tolerance():
    try:
        return float(json.loads((ROOT / "controls" / "config.json").read_text(encoding="utf-8")).get("baseline_tolerance_px", 0.5))
    except Exception:
        return 0.5


def run(target, viewport="desktop", figures_path=None, mode=None):
    from playwright.sync_api import sync_playwright
    mode = mode or load_mode()
    if mode not in ("baseline_to_capheight", "ink_to_ink"):
        return {"error": f"unknown measuring mode {mode!r}, so no measurement was taken"}
    data = json.loads(Path(figures_path or ROOT / "controls" / "design-figures.json").read_text(encoding="utf-8"))
    figures = data["figures"]
    required_fonts = data.get("required_fonts", [])
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
        loaded = page.evaluate("Array.from(document.fonts).filter(f => f.status === 'loaded').map(f => f.family.replace(/[\\\"']/g, ''))")
        missing = [fam for fam in required_fonts if fam not in loaded]
        if missing:
            browser.close()
            return {"error": "these fonts are not loaded on the page, so letters cannot be measured truthfully: " + ", ".join(missing)}
        first = measure_once(page, figures, viewport, mode)
        page.wait_for_timeout(300)
        second = measure_once(page, figures, viewport, mode)
        browser.close()
    report = []
    for f in figures:
        fid = f["id"]
        if fid not in first:
            continue
        a, b = first[fid], second[fid]
        tol = f.get("tolerance", 0)
        if mode == "baseline_to_capheight":
            tol = max(tol, load_tolerance())  # font-based readings are fractional (for example 25.4)
        row = {"id": fid, "what": f["text"], "expected": f.get("expected"), "tolerance": tol}
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
    standard = ("letters to letters (line the letters sit on to top of the capitals below)" if mode == "baseline_to_capheight"
                else "letters to letters (ink to ink)")
    return {"viewport": viewport, "mode": mode, "standard": standard, "figures": report}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("page")
    ap.add_argument("--viewport", default="desktop", choices=list(VIEWPORTS))
    ap.add_argument("--figures")
    ap.add_argument("--mode", choices=["baseline_to_capheight", "ink_to_ink"])
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    res = run(a.page, a.viewport, a.figures, a.mode)
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
