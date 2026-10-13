"""Runs the spacing and wording checks on a page. Only if nothing failed does it issue the receipt
that lets the page be sent as a preview. Usage: python3 tools/preview_gate.py <page.html> <source.docx|.txt|.md>"""
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

import measure_spacing, check_wording  # noqa: E402

for vp in ("desktop", "phone"):
    res = measure_spacing.run(str(page), vp)
    if "error" in res:
        problems.append(f"{vp}: {res['error']}")
        continue
    for r in res["figures"]:
        if r["state"] in ("FAIL", "REJECTED"):
            problems.append(f"{vp} figure {r['id']}: {r['state']} - {r.get('why') or ('measured ' + str(r.get('values')) + ', wanted ' + str(r['expected']))}")
        elif r["state"] == "NOT CHECKED":
            unchecked.append(f"{vp} figure {r['id']}")

diffs, na, nb = check_wording.compare(page.read_text(encoding="utf-8"), check_wording.source_text(source))
if diffs:
    problems.append(f"wording differs from the Word text in {len(diffs)} places (first: {diffs[0]['kind']} \"{diffs[0]['word']}\")")

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
                                         "not_checked": sorted(set(unchecked))}), encoding="utf-8")
print("PREVIEW ALLOWED. Spacing and wording checks passed for this exact file.")
if unchecked:
    print("NOT CHECKED (say so in the reply): " + ", ".join(sorted(set(unchecked))))
