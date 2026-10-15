"""Runs the spacing and wording checks on a page. Only if nothing failed does it issue the receipt
that lets the page be sent as a preview. Usage: python3 tools/preview_gate.py <page.html> <source.docx|.txt|.md>

14 Oct 2026, the owner's decision (a): the wording check reports, it does not block. Every word on the page that
differs from the Word text is printed here and kept in the receipt, and the reply must list them. A spacing failure
still blocks the preview."""
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

if len(sys.argv) != 3:
    print("Usage: python3 tools/preview_gate.py <page.html> <source.docx|.txt|.md>")
    sys.exit(1)
page, source = Path(sys.argv[1]), Path(sys.argv[2])
figs = json.loads((ROOT / "controls" / "design-figures.json").read_text(encoding="utf-8"))
problems, unchecked = [], []

# ---- the owner's decision of 15 Oct 2026 (A=1): no number reaches a page unless it came from the owner, and nothing is previewed while a question is open
import os  # noqa: E402
import re  # noqa: E402
sys.path.insert(0, str(ROOT / ".claude" / "hooks"))
os.environ.setdefault("CLAUDE_PROJECT_DIR", str(ROOT))
from lib import load_config, open_questions, approved_numbers, canon_number, normalise_quote  # noqa: E402

gate_cfg = load_config()
for q in open_questions():
    problems.append(f"{q['id']} is still open: {q['text']} (the owner answers by typing {q['id']}: <option number>)")
brief_file = ROOT / ".session" / "briefs" / f"{page.stem}.json"
brief = None
if brief_file.exists():
    brief = json.loads(brief_file.read_text(encoding="utf-8"))
else:
    problems.append(f"no build brief is filed for {page.stem}: file it with python3 tools/brief.py {page.stem} --word <file.docx> --heading \"<line>\" VALUE::LABEL::SOURCE ...")
page_html = page.read_text(encoding="utf-8")
approved = approved_numbers(None) | {canon_number(x) for x in gate_cfg.get("gate_always_allowed", [])}
if brief:
    approved |= {canon_number(b["value"]) for b in brief.get("numbers", [])}
props = gate_cfg.get("gate_spacing_properties", "margin|padding|width|height")
declarations = []
css_blocks = re.findall(r"<style[^>]*>(.*?)</style>", page_html, re.S | re.I)
for css in css_blocks:
    css = re.sub(r"/\*.*?\*/", " ", css, flags=re.S)
    css = re.sub(r"@(?:media|supports|container)[^{]*", " ", css)
    for body in re.findall(r"\{([^{}]*)\}", css):
        declarations += re.findall(r"(?<![\w-])(" + props + r")\s*:\s*([^;{}]+)", body)
for inline in re.findall(r'style\s*=\s*"([^"]*)"', page_html, re.I):
    declarations += re.findall(r"(?<![\w-])(" + props + r")\s*:\s*([^;{}]+)", inline)
unapproved = []
for prop, val in declarations:
    if re.search(r"var\(|url\(|calc\(|clamp\(|min\(|max\(", val):
        continue
    for num, unit in re.findall(r"(?<![\w#.])(-?\d*\.?\d+)(px|em|rem|%|pt|vh|vw|ch)?", val):
        if not unit and prop != "line-height":
            continue
        n = canon_number(abs(float(num)))
        if n not in approved:
            unapproved.append(f"{prop}: {val.strip()[:40]} (the number {n})")
if unapproved:
    shown = sorted(set(unapproved))
    problems.append(f"{len(shown)} number(s) on this page are not an approved figure and not in the brief, so the preview is blocked until the owner decides them: "
                    + "; ".join(shown[:12]) + ('; ...' if len(shown) > 12 else '')
                    + ". Raise each as a question: python3 tools/ask.py \"<question>\" \"<option 1>\" \"<option 2>\"")
if brief:
    brief_heads = {normalise_quote(h) for h in brief.get("headings", [])}
    page_heads = {normalise_quote(re.sub(r"<[^>]+>", " ", t)) for _, t in re.findall(r"<h([1-6])[^>]*>(.*?)</h\1>", page_html, re.S | re.I)}
    page_heads.discard("")
    stray = sorted(page_heads - brief_heads)
    if stray:
        problems.append("these headings on the page are not in the brief's heading map: " + "; ".join(stray[:8]))

import measure_spacing, check_wording  # noqa: E402

for vp in ("desktop", "phone"):
    try:
        res = measure_spacing.run(str(page), vp)
    except Exception as exc:  # a measurement that cannot run is never a pass
        res = {"error": f"the spacing measurement could not run ({exc})"}
    if "error" in res:
        problems.append(f"{vp}: {res['error']}")
        continue
    for r in res["figures"]:
        if r["state"] in ("FAIL", "REJECTED"):
            problems.append(f"{vp} figure {r['id']}: {r['state']} - {r.get('why') or ('measured ' + str(r.get('values')) + ', wanted ' + str(r['expected']))}")
        elif r["state"] == "NOT CHECKED":
            unchecked.append(f"{vp} figure {r['id']}")

diffs, na, nb = check_wording.compare(page.read_text(encoding="utf-8"), check_wording.source_text(source))
wording = [f"{d['kind']}: Word \"{d['word']}\" / page \"{d['page']}\" (after: ...{d['context']})" for d in diffs]

if unchecked and figs.get("block_preview_if_unmapped"):
    problems.append("these figures could not be checked yet: " + ", ".join(sorted(set(unchecked))[:10]))

if problems:
    print("PREVIEW NOT ALLOWED. Problems:")
    for p in problems:
        print("  - " + p)
    sys.exit(1)

h = hashlib.sha256(page.read_bytes()).hexdigest()
d = ROOT / ".session" / "receipts"
d.mkdir(parents=True, exist_ok=True)
(d / f"{h}.json").write_text(json.dumps({"page": str(page), "source": str(source), "ts": time.time(),
                                         "not_checked": sorted(set(unchecked)), "wording_differences": wording}), encoding="utf-8")
print("PREVIEW ALLOWED. The spacing check passed for this exact file.")
if wording:
    print(f"WORDING DIFFERS from the Word text in {len(wording)} places (list them in the reply):")
    for w in wording:
        print("  - " + w)
else:
    print("WORDING MATCHES the Word text word for word.")
if unchecked:
    print("NOT CHECKED (say so in the reply): " + ", ".join(sorted(set(unchecked))))
