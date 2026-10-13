"""Stop: a reply cannot be finished unless it (1) reports what was searched and what could not be, matching the log,
and (2) says what was looked at whenever it claims something is checked or done."""
import json
import re
from lib import *

ev = read_event()
sid = ev.get("session_id")
cfg = load_config()
st = load_state(sid)
turn = int(st.get("turn", 0))

msg = ev.get("last_assistant_message")
if not msg:
    try:
        last = ""
        for line in open(ev.get("transcript_path", ""), encoding="utf-8"):
            d = json.loads(line)
            m = d.get("message", d)
            if m.get("role") == "assistant":
                c = m.get("content")
                t = c if isinstance(c, str) else "".join(b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text")
                if t.strip():
                    last = t
        msg = last
    except Exception:
        msg = ""
msg = msg or ""

NAMES = sorted(cfg["required_places"] + cfg["extra_places"], key=len, reverse=True)
FOOT = re.compile(r"^\W*(searched|couldn[’']?t search|could not search|looked at)\s*\W*:\s*(.*)$", re.I)


def footer_lines(text):
    found = {}
    body = []
    for line in text.splitlines():
        m = FOOT.match(line.strip())
        if m:
            k = m.group(1).lower()
            k = "searched" if k == "searched" else ("looked" if k == "looked at" else "couldnt")
            found[k] = m.group(2).strip()
        else:
            body.append(line)
    return found, "\n".join(body)


def mentioned(line):
    out, rest = [], line.lower()
    for n in NAMES:
        if n.lower() in rest:
            out.append(n)
            rest = rest.replace(n.lower(), " ")
    return out


foot, body = footer_lines(msg)
use = (lambda r: r.get("turn") == turn) if cfg.get("search_scope", "turn") == "turn" else (lambda r: True)
log = [r for r in read_log(sid) if r.get("event") == "tool" and use(r)]
ok_places = set(p for r in log if r.get("ok") for p in r.get("places", []))
failed_places = set(p for r in log if not r.get("ok") for p in r.get("places", []))
declared = {d["place"] for d in read_declared(sid) if use(d)}
problems = []

if "searched" not in foot or "couldnt" not in foot:
    problems.append('The reply must end with two lines: "Searched: ..." and "Couldn\'t search: ..." (write "none" if everything was searched).')
else:
    searched = mentioned(foot["searched"])
    couldnt_line = foot["couldnt"]
    couldnt = [] if re.match(r"^\W*none\W*$", couldnt_line, re.I) else mentioned(couldnt_line)
    for p in searched:
        if p not in ok_places:
            problems.append(f'"{p}" is listed as searched but nothing in the log shows it was searched in this reply.')
    for p in cfg["required_places"]:
        if p not in searched and p not in couldnt:
            problems.append(f'"{p}" is in neither line. Every place must be under Searched or Couldn\'t search.')
    chunks = [c for c in re.split(r";|\n", couldnt_line) if c.strip()]
    for p in couldnt:
        chunk = next((c for c in chunks if p.lower() in c.lower()), "")
        reason = next((r for r in cfg["unavailable_reasons_allowed"] if r in chunk.lower()), None)
        if p in ok_places:
            problems.append(f'"{p}" was searched successfully, so list it under Searched, not Couldn\'t search.')
        elif not reason:
            problems.append(f'"{p}" needs one of these reasons: ' + "; ".join(cfg["unavailable_reasons_allowed"]) + ".")
        elif reason == "not offered in this session" and p not in declared:
            problems.append(f'Record "{p}" first with: python3 tools/declare.py "{p}" "not offered in this session"')
        elif reason == "tool call failed" and p not in failed_places:
            problems.append(f'"{p}" says the tool call failed, but no failed call is in the log for this reply.')

if re.search(cfg["claim_words_regex"], body):
    if "looked" not in foot or not foot["looked"].strip():
        problems.append('The reply says something is checked, done, matches, measured or fixed, so it must also end with "Looked at: ..." naming what was looked at (separated by semicolons).')
    else:
        targets = [t.lower() for r in log for t in r.get("targets", []) if isinstance(t, str) and len(t) >= 4]
        for item in [i.strip() for i in foot["looked"].split(";") if i.strip()]:
            il = item.lower()
            if il in (n.lower() for n in NAMES):
                continue
            if not any(il in t or t in il for t in targets):
                problems.append(f'"Looked at" lists "{item}", but no tool call in this reply touched it.')

if not problems:
    sys.exit(0)

blocks = st.setdefault("blocks", {})
blocks["stop"] = int(blocks.get("stop", 0)) + 1
save_state(sid, st)
if blocks["stop"] > int(cfg.get("max_blocks_per_reply", 5)):
    append_log(sid, {"turn": turn, "event": "VIOLATION", "problems": problems})
    print(json.dumps({"systemMessage": "A check was not satisfied after several tries and the reply was let through. "
                                       "Problems: " + " | ".join(problems[:4])}))
    sys.exit(0)
print(json.dumps({"decision": "block", "reason": "Reply not finished. Fix these, then finish again:\n- " + "\n- ".join(problems[:10])}))
sys.exit(0)
