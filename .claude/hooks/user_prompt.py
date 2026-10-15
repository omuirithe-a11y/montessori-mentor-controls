"""UserPromptSubmit: marks the start of a new turn, records the owner's own words, and tells Claude what to search for.
Only the owner's typed message can create a "go" or a "push" permission - Claude cannot.
Owner's decision of 14 Oct 2026: the search words are the owner's, and the search comes before anything is written."""
import json
import os
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
words, content = words_from(prompt[:2000])
st["search_content"] = content
append_prompt(sid, st["turn"], prompt)  # the full text, in the session folder Claude cannot write to
closed = close_from_prompt(prompt)
save_state(sid, st)
append_log(sid, {"turn": st["turn"], "event": "owner_message", "chars": len(prompt),
                 "go": st["go_turn"] == st["turn"], "push_words": st["push_ok_turn"] == st["turn"], "content_words": content})

# What Claude is told the moment the owner's message arrives: search first, with these words, then quote what was found.
tool_cmd = 'python3 "$HOME/.mm-controls/tools/search.py"' if os.environ.get("MM_USER_LEVEL") else "python3 tools/search.py"
lines = ["SEARCH FIRST, BEFORE WRITING A WORD OF THE REPLY (the owner's standing instruction; the end-of-reply check refuses a reply without it).",
         "1. Run: " + tool_cmd + "   - it searches this repository and the records with the owner's own words"
         + (": " + ", ".join(content) if content else " (this message has no content words; the run still records that)") + ".",
         "2. Search Google Drive, Artifacts, Claude docs and Skills with the same words. The Drive query must carry one of them.",
         "3. In the reply, quote what was found word for word. Never say nothing was found while the search log holds matches.",
         "4. Do not ask about anything the settled list (controls/settled.json) already answers; use the answer.",
         "5. If a check blocks the reply, that is an instruction to go back and do the missing work, not a place to stop. Keep searching (wider words, more places, a fresh subagent) until the result can be shown. Never end with \"a check stopped me\"."]
for q in closed:
    lines.append(f"ANSWERED by the owner: {q['id']} -> option {q['answer']}: {q['answer_text']}  (their words are recorded in controls/decisions.json). Use the answer; do not ask again.")
if not closed and re.search(r"(?i)\bQ\d+\b", prompt):
    lines.append("The owner's message names a question but is not in the form 'Q<number>: <option number>' for an open question, so nothing was recorded. Ask them to answer by number only, for example Q4: 2.")
oq = open_questions()
if oq:
    lines.append("STILL OPEN, nothing that depends on these may be built, previewed, sent, published or pushed: " + " | ".join(f"{q['id']}: {q['text']}" for q in oq))
touched = settled_matches(prompt, load_settled()) if content else []
if touched:
    lines.append("SETTLED DECISIONS THIS MESSAGE TOUCHES - use them, do not ask about them:")
    for e, present in touched[:8]:
        lines.append(f"- {e.get('topic', '')} ({e.get('date', '')}): {e.get('answer', '')}")
print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": "\n".join(lines)}}))
sys.exit(0)
