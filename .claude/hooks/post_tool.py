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


def excerpt(resp, limit=None):
    """A flat excerpt of what the tool printed (the start and the end, where ids and links usually are), so the independent reviewer can check claims about results.
    The size is claim_reviewer.result_chars in controls/config.json (owner's request, 15 Oct 2026: let the reviewer see more)."""
    limit = limit or int(cfg.get("claim_reviewer", {}).get("result_chars", 2500))
    if isinstance(resp, dict):
        resp = resp.get("stdout") or resp.get("output") or resp.get("content") or resp.get("text") or json.dumps(resp, ensure_ascii=False)
    if isinstance(resp, list):
        resp = " ".join(str(b.get("text", b)) if isinstance(b, dict) else str(b) for b in resp)
    s = " ".join(str(resp or "").split())
    return s if len(s) <= limit else s[:limit // 2] + " ... " + s[-limit // 2:]


rec["result"] = excerpt(ev.get("tool_response") or ev.get("error"))  # a failed call carries its reason in "error"
append_log(sid, rec)

sys.exit(0)
