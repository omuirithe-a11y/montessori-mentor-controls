"""Record a topic the owner has told Claude to drop. Usage: python3 tools/order.py drop "<term>" ["<term>" ...]
Each term must be words the owner typed in this turn's message (the check refuses any other); a reply that contains a recorded term is refused.
Also: python3 tools/order.py list   (prints the owner's orders and the dropped topics)
The owner's messages themselves are recorded by the automatic checks, not by this tool. Only the checks write controls/orders.json."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / ".claude" / "hooks"))
os.environ.setdefault("CLAUDE_PROJECT_DIR", str(Path(__file__).resolve().parent.parent))
from lib import *  # noqa: E402

args = sys.argv[1:]
if not args:
    print(__doc__)
    sys.exit(1)

if args[0] == "list":
    for o in read_orders()["orders"][-20:]:
        flag = " [DROP: " + ", ".join(o.get("terms", [])) + "]" if o.get("drop") else ""
        print(f"{o['id']} {o['date']}{flag}: {o['words'][:300]}")
    sys.exit(0)

if args[0] != "drop" or len(args) < 2:
    print(__doc__)
    sys.exit(1)

sid = current_session_id()
if not sid:
    print("No session id is available, so the topic cannot be recorded. Tell the owner.")
    sys.exit(1)
st = load_state(sid)
turn = int(st.get("turn", 0))
terms = [a.strip() for a in args[1:] if a.strip()]
o = add_drop_terms(sid, turn, terms)
if not o:
    print("NOT RECORDED: the owner's message of this turn is not a message that drops a topic, so there is nothing to attach the terms to.")
    sys.exit(1)
bad = [t for t in terms if t not in o.get("terms", [])]
if bad:
    print("NOT RECORDED (not the owner's own words in this turn's message): " + "; ".join(bad))
    print("Use words the owner typed, exactly. Recorded so far: " + (", ".join(o.get("terms", [])) or "none"))
    sys.exit(1)
append_log(sid, {"turn": turn, "event": "drop_recorded", "id": o["id"], "terms": o["terms"]})
print(f"RECORDED {o['id']}: from now on a reply containing any of these is refused: " + ", ".join(o["terms"]) + ". Do not mention them again.")
