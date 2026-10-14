"""Stop: a reply cannot be finished unless it (1) reports what was searched and what could not be, matching the log,
(2) says what was looked at whenever it claims something is checked or done, and - the owner's decision of 14 Oct 2026 -
(3) the owner's message was searched with the owner's own words, in this repository and in Google Drive,
(4) what the search found is quoted in the reply, (5) the reply does not say nothing was found while the log holds matches
or lean on a record it did not read, and (6) the reply does not ask a question the settled list already answers."""
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
searches = [s for s in read_searches(sid) if use(s)]
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

# ---------------------------------------------------------------- the search must be the owner's, and used (14 Oct 2026)
content = [c for c in st.get("search_content", []) if c] if cfg.get("search_scope", "turn") == "turn" else []
tool = cfg.get("search_tool", "tools/search.py")
message_search = next((s for s in searches if s.get("source") == "owner's message" and covers(content, s.get("content", []))), None)

if content and turn > 0:
    # (3) the owner's message searched with the owner's words, here and in Google Drive
    if not message_search:
        problems.append(f"The owner's message was not searched with the owner's own words. Run first: python3 {tool}   "
                        "(no arguments: it takes the words from the message), then search the other places with the words it prints.")
    drive = [r for r in log if r.get("ok") and "Google Drive" in r.get("places", [])]
    if drive:
        queries = " ".join(t for r in drive for t in r.get("targets", []) if isinstance(t, str)).lower()
        if not any(any(f in queries for f in forms(c)) for c in content):
            problems.append("Google Drive was searched, but not with the owner's words. Search it again with one of: " + ", ".join(content[:12]) + ".")

if message_search:
    body_norm = normalise_quote(body)
    body_words = body_norm.split()
    min_words = int(cfg.get("quote_min_words", 5))

    def quoted(line_text):
        ws = normalise_quote(line_text).split()
        if not ws:
            return False
        if len(ws) <= min_words:
            return " " + " ".join(ws) + " " in " " + body_norm + " " if len(ws) >= 2 else False
        for i in range(0, len(ws) - min_words + 1):
            if " " + " ".join(ws[i:i + min_words]) + " " in " " + body_norm + " ":
                return True
        return False

    # (4) what was found must be used: for every place with strong matches, one matching line quoted word for word
    for place, d in (message_search.get("places") or {}).items():
        strong = [l for l in d.get("lines", []) if l.get("strong")]
        if not strong:
            continue
        if not any(quoted(l.get("text", "")) for l in strong):
            sample = "; ".join(f"{l['file']}:{l['line']} \"{l['text'][:90]}\"" for l in strong[:3])
            problems.append(f'The search found {len(strong)} strong match(es) in {place} and the reply quotes none of them. '
                            f'Quote at least {min_words} consecutive words of one matching line word for word (or say what it says and why it does not apply, quoting it). For example: {sample}')

    # (5) "nothing found" is refused while the log holds matches
    total_strong = sum(int(d.get("strong", 0)) for d in (message_search.get("places") or {}).values())
    if total_strong and re.search(cfg.get("not_found_regex", "$^"), body):
        files = sorted({l["file"] for d in message_search["places"].values() for l in d.get("lines", []) if l.get("strong")})[:6]
        problems.append('The reply says nothing was found, but the search log holds strong matches in: ' + ", ".join(files) + ". Say what they say.")

# (5b) a record quoted as evidence must have been read or searched in this reply
if re.search(cfg.get("records_claim_regex", "$^"), body):
    targets = " ".join(t for r in log if r.get("ok") for t in r.get("targets", []) if isinstance(t, str)).lower()
    read_record = re.search(r"(start-here\.md|project-instructions\.md|/records/|settled\.json|config\.json)", targets)
    searched_record = any(int((s.get("places") or {}).get(p, {}).get("matches", 0)) for s in searches for p in ("Records", "Project instructions"))
    if not read_record and not searched_record:
        problems.append("The reply leans on what a record says (START-HERE, the project instructions, the records or the settled list), "
                        "but nothing in this reply read or searched them. Read the file, then quote it.")

# (6) a settled question is refused with its answer, unless the owner raised it themselves this turn
settled = load_settled()
if settled:
    owner_text = str(st.get("last_prompt", ""))
    owner_touched = {e.get("id") for e, _ in settled_matches(owner_text, settled)} if content else set()
    for q in questions_in(body):
        for e, present in settled_matches(q, settled):
            if e.get("id") in owner_touched:
                continue
            problems.append(f'The reply asks "{q[:120]}", but that is settled ({e.get("date", "")}): {e.get("answer", "")} '
                            f'Use the answer instead of asking. (Matched: {", ".join(present)}; source: {e.get("source", "")}.)')

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
