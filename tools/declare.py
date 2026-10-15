"""Record that named places could not be searched, and why.
Usage: python3 tools/declare.py "<place>" "<reason>"
       python3 tools/declare.py --places "<reason>" "<place>" "<place>" ...      (several places, one reason)
       python3 tools/declare.py --cloud-defaults                                  (the five places a cloud session never offers)
The reason must be one of the allowed reasons. A place that was already searched successfully cannot be declared unavailable."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / ".claude" / "hooks"))
os.environ.setdefault("CLAUDE_PROJECT_DIR", str(Path(__file__).resolve().parent.parent))
from lib import *  # noqa: E402

cfg = load_config()
args = sys.argv[1:]
if args[:1] == ["--cloud-defaults"] and len(args) == 1:
    reason, places = "not offered in this session", list(cfg.get("cloud_unavailable_places", []))
elif args[:1] == ["--places"] and len(args) >= 3:
    reason, places = args[1], args[2:]
elif len(args) == 2:
    places, reason = [args[0]], args[1]
else:
    print(__doc__)
    sys.exit(1)
sid = os.environ.get("CLAUDE_SESSION_ID")
if not sid:
    print("No session id is available, so this cannot be recorded. Tell the owner.")
    sys.exit(1)
if not any(reason.lower().startswith(r) for r in cfg["unavailable_reasons_allowed"]):
    print("Reason not allowed. Use one of: " + "; ".join(cfg["unavailable_reasons_allowed"]))
    sys.exit(1)
known = cfg["required_places"] + cfg["extra_places"]
st = load_state(sid)
turn = int(st.get("turn", 0))
scope_turn = cfg.get("search_scope") == "turn"
code = 0
for place in places:
    if place not in known:
        print(f"Unknown place: {place}. Allowed: " + "; ".join(known))
        code = 1
        continue
    if any(r.get("event") == "tool" and r.get("ok") and place in r.get("places", []) and (not scope_turn or r.get("turn") == turn)
           for r in read_log(sid)):
        print(f"{place} was already searched successfully this {'reply' if scope_turn else 'session'}. List it under Searched, not under Couldn't search.")
        code = 1
        continue
    append_declared(sid, place, reason, turn)
    print(f"Recorded: {place} - {reason}")
sys.exit(code)
