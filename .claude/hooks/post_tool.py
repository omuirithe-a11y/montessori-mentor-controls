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


def excerpt(resp, limit=700):
    """A short, flat excerpt of what the tool printed, so the independent reviewer can check claims about results."""
    if isinstance(resp, dict):
        resp = resp.get("stdout") or resp.get("output") or resp.get("content") or resp.get("text") or json.dumps(resp, ensure_ascii=False)
    if isinstance(resp, list):
        resp = " ".join(str(b.get("text", b)) if isinstance(b, dict) else str(b) for b in resp)
    s = " ".join(str(resp or "").split())
    return s if len(s) <= limit else s[:limit // 2] + " ... " + s[-limit // 2:]


rec["result"] = excerpt(ev.get("tool_response"))
append_log(sid, rec)

sys.exit(0)
