"""Record that a named place could not be searched, and why. Usage: python3 tools/declare.py "<place>" "<reason>"
The reason must be one of the allowed reasons. A place that was already searched successfully cannot be declared unavailable."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / ".claude" / "hooks"))
os.environ.setdefault("CLAUDE_PROJECT_DIR", str(Path(__file__).resolve().parent.parent))
from lib import *  # noqa: E402

if len(sys.argv) != 3:
    print('Usage: python3 tools/declare.py "<place>" "<reason>"')
    sys.exit(1)
place, reason = sys.argv[1], sys.argv[2]
cfg = load_config()
sid = os.environ.get("CLAUDE_SESSION_ID")
if not sid:
    print("No session id is available, so this cannot be recorded. Tell the owner.")
    sys.exit(1)
if place not in cfg["required_places"] + cfg["extra_places"]:
    print("Unknown place. Allowed: " + "; ".join(cfg["required_places"] + cfg["extra_places"]))
    sys.exit(1)
if not any(reason.lower().startswith(r) for r in cfg["unavailable_reasons_allowed"]):
    print("Reason not allowed. Use one of: " + "; ".join(cfg["unavailable_reasons_allowed"]))
    sys.exit(1)
st = load_state(sid)
turn = int(st.get("turn", 0))
scope_turn = cfg.get("search_scope") == "turn"
for r in read_log(sid):
    if r.get("event") == "tool" and r.get("ok") and place in r.get("places", []) and (not scope_turn or r.get("turn") == turn):
        print(f"{place} was already searched successfully this {'reply' if scope_turn else 'session'}. List it under Searched, not under Couldn't search.")
        sys.exit(1)
append_declared(sid, place, reason, turn)
print(f"Recorded: {place} - {reason}")
