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

# Check the Drive copy of START-HERE against the copy in this repository.
sh = cfg["start_here"]
if (not failed and tool == "mcp__Google_Drive__read_file_content" and ti.get("fileId") == sh["drive_file_id"]):
    resp = ev.get("tool_response")
    text = resp if isinstance(resp, str) else json.dumps(resp, ensure_ascii=False)
    try:
        # tool_response may be a JSON string or a dict holding "fileContent"
        obj = resp if isinstance(resp, dict) else json.loads(text)
        if isinstance(obj, dict):
            if "fileContent" in obj:
                text = obj["fileContent"]
            elif isinstance(obj.get("content"), list):
                text = "".join(c.get("text", "") for c in obj["content"] if isinstance(c, dict))
                try:
                    inner = json.loads(text)
                    text = inner.get("fileContent", text)
                except Exception:
                    pass
    except Exception:
        pass
    drive_norm = normalise_markdown(text)
    copy = (project_dir() / sh["copy_path"]).read_text(encoding="utf-8")
    if sha256_text(drive_norm) == sha256_text(normalise_markdown(copy)):
        st["start_here_status"] = "match"
    else:
        st["start_here_status"] = "MISMATCH"
        print("START-HERE in Google Drive is different from the copy in this repository. "
              "Stop and tell the owner in plain English. No change is allowed until the owner decides which is right.",
              file=sys.stderr)
        save_state(sid, st)
        sys.exit(2)  # PostToolUse exit 2 shows stderr to Claude
    save_state(sid, st)
sys.exit(0)
