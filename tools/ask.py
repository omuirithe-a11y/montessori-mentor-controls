"""Put a decision to the owner. Usage: python3 tools/ask.py "<question>" "<option 1>" "<option 2>" ["<option 3>" ...]
It records the question as OPEN in controls/decisions.json and prints the exact text that must go in the reply.
Only the owner can close a question, by typing "Q<number>: <option number>". Claude cannot record an answer.
While any question is open nothing is built, previewed, sent, published or pushed.
A question the owner has already answered, or that controls/settled.json settles, is not asked again: the answer is printed instead."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / ".claude" / "hooks"))
os.environ.setdefault("CLAUDE_PROJECT_DIR", str(Path(__file__).resolve().parent.parent))
from lib import *  # noqa: E402

args = sys.argv[1:]
if len(args) < 3:
    print(__doc__)
    sys.exit(1)
text, options = args[0].strip(), [a.strip() for a in args[1:] if a.strip()]
if len(options) < 2:
    print("A question needs at least two numbered options.")
    sys.exit(1)
sid = current_session_id()
if not sid:
    print("No session id is available, so the question cannot be recorded. Tell the owner.")
    sys.exit(1)

settled = settled_matches(text, load_settled())
if settled:
    e = settled[0][0]
    print(f"NOT ASKED: this is settled ({e.get('date', '')}, {e.get('source', '')}): {e.get('answer', '')}\nUse the answer.")
    sys.exit(1)

norm = normalise_quote(text)
for q in read_register()["questions"]:
    if normalise_quote(q.get("text", "")) == norm:
        if q.get("status") == "answered":
            print(f"NOT ASKED: the owner already answered {q['id']} on {q.get('answered')}: option {q['answer']} - {q['answer_text']}\nUse the answer.")
            sys.exit(1)
        print(f"ALREADY OPEN: {q['id']}. Put this in the reply and wait for the owner's answer:\n")
        print(f"{q['id']}. {q['text']}")
        for i, o in enumerate(q["options"], 1):
            print(f"{i}. {o}")
        print(f"Answer with: {q['id']}: <number>")
        sys.exit(0)

st = load_state(sid)
q = raise_question(text, options, sid, int(st.get("turn", 0)))
append_log(sid, {"turn": int(st.get("turn", 0)), "event": "question_raised", "id": q["id"]})
print(f"RAISED {q['id']}. Put exactly this in the reply, then build nothing until the owner answers \"{q['id']}: <number>\":\n")
print(f"{q['id']}. {q['text']}")
for i, o in enumerate(q["options"], 1):
    print(f"{i}. {o}")
print(f"Answer with: {q['id']}: <number>")
