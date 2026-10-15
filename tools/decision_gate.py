"""The decision-gate check (runs on every pull request and push on GitHub, and can be run by hand): python3 tools/decision_gate.py
It fails when (1) the decision register holds an open question, or (2) a design figure in START-HERE and the figures file disagree on a number.
Owner's decision of 15 Oct 2026 (D=1: the register lives in the repository, so GitHub can refuse to merge while a question is open)."""
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / ".claude" / "hooks"))
os.environ["CLAUDE_PROJECT_DIR"] = str(ROOT)
from lib import *  # noqa: E402

problems = []

# 1. no open question may reach the approved version
for q in open_questions():
    problems.append(f"{q['id']} is still open ({q.get('raised', '')}): {q['text']}  - the owner answers by typing {q['id']}: <option number>")

# 2. START-HERE and the figures file must agree
lines = figure_lines()
try:
    figs = json.loads((ROOT / "controls" / "design-figures.json").read_text(encoding="utf-8")).get("figures", [])
except Exception as exc:
    figs = []
    problems.append(f"controls/design-figures.json could not be read: {exc}")
for f in figs:
    fid = f.get("id")
    exp = f.get("expected")
    if exp is None:
        continue
    text = lines.get(fid)
    if text is None:
        problems.append(f"figure {fid} is in the figures file but not in START-HERE's design figures")
    elif canon_number(exp) not in numbers_in(text):
        problems.append(f"figure {fid}: START-HERE says \"{text}\" but the figures file expects {canon_number(exp)}")

if problems:
    print("DECISION GATE FAILED:")
    for p in problems:
        print("  - " + p)
    sys.exit(1)
print(f"DECISION GATE PASSED: no open question; {len(figs)} figures agree with START-HERE.")
