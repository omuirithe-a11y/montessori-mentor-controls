"""PostToolUse / PostToolUseFailure: keeps the search log. Claude cannot write to this log - only this check can."""
import json
from lib import *

ev = read_event()
sid = ev.get("session_id")
cfg = load_config()
st = load_state(sid)
tool = ev.get("tool_name", "")
ti = ev.get("tool_input") or {}
failed = ev.get("hook_event_name") == "PostToolUseFailure"
places = places_for(tool, ti)
rec = {"turn": st.get("turn", 0), "event": "tool", "tool": tool, "ok": not failed,
       "places": places, "targets": targets_for(tool, ti)}
append_log(sid, rec)

sys.exit(0)
