"""UserPromptSubmit: marks the start of a new turn, and records the owner's own words.
Only the owner's typed message can create a "go" or a "push" permission - Claude cannot."""
import re
from lib import *

ev = read_event()
sid = ev.get("session_id")
cfg = load_config()
st = load_state(sid)
st["turn"] = int(st.get("turn", 0)) + 1
prompt = str(ev.get("prompt", ""))
st["blocks"] = {}
st["last_prompt"] = prompt[:2000]
st["go_turn"] = st["turn"] if re.match(cfg["go_regex"], prompt) else st.get("go_turn")
st["push_ok_turn"] = st["turn"] if re.search(cfg["push_words_regex"], prompt) else st.get("push_ok_turn")
save_state(sid, st)
append_log(sid, {"turn": st["turn"], "event": "owner_message", "chars": len(prompt),
                 "go": st["go_turn"] == st["turn"], "push_words": st["push_ok_turn"] == st["turn"]})
sys.exit(0)
