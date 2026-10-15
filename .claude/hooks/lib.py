"""Shared helpers for the automatic checks (hooks). Python standard library only."""
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path


def project_dir() -> Path:
    return Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()).resolve()


def load_config() -> dict:
    return json.loads((project_dir() / "controls" / "config.json").read_text(encoding="utf-8"))


def read_event() -> dict:
    raw = sys.stdin.read()
    ev = json.loads(raw) if raw.strip() else {}
    try:  # every check leaves the live session id where the tools can find it if the start check never ran (owner's decision of 15 Oct 2026, option 2)
        if ev.get("session_id"):
            d = project_dir() / ".session"
            d.mkdir(parents=True, exist_ok=True)
            (d / "current").write_text(safe_id(ev["session_id"]), encoding="utf-8")
    except Exception:
        pass
    return ev


def current_session_id():
    """The session id for the tools: the environment first, else the id the checks last left in .session/current (only if it is under 12 hours old)."""
    sid = os.environ.get("CLAUDE_SESSION_ID")
    if sid:
        return sid
    try:
        f = project_dir() / ".session" / "current"
        if f.is_file() and time.time() - f.stat().st_mtime < 12 * 3600:
            return f.read_text(encoding="utf-8").strip() or None
    except Exception:
        pass
    return None


def safe_id(session_id) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", session_id or "nosession")[:80]


def state_dir(session_id) -> Path:
    d = project_dir() / ".session" / safe_id(session_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_state(session_id) -> dict:
    p = state_dir(session_id) / "state.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"turn": 0, "go_turn": None, "push_ok_turn": None, "blocks": {}, "tampered": False,
            "start_here_status": "not checked", "notes": []}


def save_state(session_id, state: dict) -> None:
    p = state_dir(session_id) / "state.json"
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=1), encoding="utf-8")
    os.replace(tmp, p)


def append_log(session_id, record: dict) -> None:
    record = dict(record)
    record["ts"] = round(time.time(), 1)
    with open(state_dir(session_id) / "log.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_log(session_id) -> list:
    p = state_dir(session_id) / "log.jsonl"
    out = []
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except Exception:
                pass
    return out


def append_declared(session_id, place: str, reason: str, turn: int) -> None:
    with open(state_dir(session_id) / "declared.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"place": place, "reason": reason, "turn": turn, "ts": round(time.time(), 1)}) + "\n")


def read_declared(session_id) -> list:
    p = state_dir(session_id) / "declared.jsonl"
    out = []
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except Exception:
                pass
    return out


def append_search(session_id, record: dict) -> None:
    record = dict(record)
    record["ts"] = round(time.time(), 1)
    with open(state_dir(session_id) / "searches.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_searches(session_id) -> list:
    p = state_dir(session_id) / "searches.jsonl"
    out = []
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except Exception:
                pass
    return out


def load_settled() -> list:
    """The owner's settled decisions (controls/settled.json). Missing or unreadable: an empty list."""
    try:
        p = project_dir() / load_config().get("settled_path", "controls/settled.json")
        d = json.loads(p.read_text(encoding="utf-8"))
        return [e for e in d.get("settled", []) if isinstance(e, dict) and e.get("words")]
    except Exception:
        return []


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- the owner's words: what a search must look for

STOP_WORDS = set('''a an the and or but if then than that this these those there their they them it its is are was were be
been being am do does did done have has had having can could will would shall should may might must not no nor of on
in into onto at by for from to with without about over up down out off again further once here
when where why how what which who whom whose all any both each few more most other some such only own same so too very
just also as you your yours i me my we our us he she his her him one two three four five six seven eight nine ten
yes ok okay please now new old get got make made let say said tell told ask asked question questions answer answers
use used way ways thing things there's it's i'm you're don't didn't isn't aren't wasn't won't can't couldn't
shouldn't wouldn't i'll you'll we'll i've you've we've i'd you'd let's whether still already ever every
because while being within upon per via etc want wants wanted need needs needed like likes give gives going keep
keeps thanks thank think know knows put give went come came take took see saw look looked something anything
everything nothing someone anyone everyone really quite rather much many less least next back well
good bad sure fine done able'''.split())

CONTENT_WORD_CAP = 40


def forms(w: str) -> set:
    """A word and its other forms - plural / singular, -ed, -ing, -ly - so one spelling cannot hide another."""
    w = w.lower()
    out = {w}
    if not re.search(r"[a-z]", w) or " " in w:
        if "-" in w:
            out |= {w.replace("-", " "), w.replace("-", "")}
        return out
    for suf in ("ing", "ed", "es", "s", "ly", "ies", "er", "ers"):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            stem = w[:-len(suf)]
            out.add(stem)
            if suf == "ies":
                out.add(stem + "y")
            if suf in ("ing", "ed") and len(stem) > 2 and stem[-1] == stem[-2]:
                out.add(stem[:-1])
    base = sorted(out, key=len)[0]
    out |= {base + "s", base + "es", base + "ed", base + "ing"}
    if "-" in w:
        out |= {w.replace("-", " "), w.replace("-", "")}
    return out


def words_from(text: str):
    """Every word a search must cover, taken from the owner's own words: (all terms, the content words).
    Terms: quoted phrases, pairs of neighbouring content words, then every content word with its forms."""
    text = text or ""
    quoted = [q.strip() for pair in re.findall(r'"([^"]{3,})"|“([^”]{3,})”', text) for q in pair if q]
    toks = re.findall(r"[A-Za-z0-9#][A-Za-z0-9#'/\-\.]*", text)
    content = []
    for t in toks:
        t = t.strip("'.").lower()
        if not t:
            continue
        if re.match(r"^#?\d+(\.\d+)*$", t) or (len(t) >= 3 and t not in STOP_WORDS and re.search(r"[a-z]", t)):
            if t not in content:
                content.append(t)
        if len(content) >= CONTENT_WORD_CAP:
            break
    pairs = [f"{a} {b}" for a, b in zip(content, content[1:])]
    terms = []
    for t in quoted + pairs:
        terms.append(t.lower())
    for t in content:
        terms.extend(sorted(forms(t)))
    seen, out = set(), []
    for t in terms:
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out, content


def normalise_quote(s: str) -> str:
    """Lower case, letters and digits only, one space between words - so a quotation is matched by its words."""
    return " ".join(re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).split())


def covers(content: list, searched_content: list) -> bool:
    """True when a search's words cover at least half of the message's content words."""
    need = [c for c in content if c]
    if not need:
        return True
    have = set(searched_content or [])
    got = sum(1 for w in need if w in have or any(f in have for f in forms(w)))
    return got * 2 >= len(need)


def word_in(text: str, word: str) -> bool:
    """A word, or any of its forms, or a phrase, present in the text."""
    low = normalise_quote(text)
    for f in forms(word) | {word.lower()}:
        f = normalise_quote(f)
        if f and re.search(r"(^|\s)" + re.escape(f) + r"(\s|$)", low):
            return True
    return False


# ---------------------------------------------------------------- questions and settled decisions

QUESTION_WH = r"(who|whom|whose|what|which|when|where|why|how|whether)"
QUESTION_AUX = (r"(is|are|was|were|am|do|does|did|have|has|had|can|could|will|would|shall|should|may|might|must|need|ought|"
                r"isn't|aren't|wasn't|weren't|don't|doesn't|didn't|haven't|hasn't|hadn't|can't|cannot|couldn't|won't|"
                r"wouldn't|shan't|shouldn't|mightn't|mustn't|needn't)")
QUESTION_SUBJ = r"(i|you|we|it|this|that|these|those|there|they|he|she|the|a|an|my|your|our|any|anything|everything|all|one)"
QUESTION_INDIRECT = [
    r"\btell me\b", r"\blet me know\b", r"\bsay (if|whether|which|when|what|so|go|the word|yes|no)\b", r"\bjust say\b",
    r"\bi need (to know|from you|your)\b", r"\bi'?d like to know\b", r"\bi (wonder|am wondering|'m wondering)\b",
    r"\b(can|could|would|will) you\b", r"\bdo you (want|prefer|mean|need|agree|like|wish)\b",
    r"\bif you (want|prefer|meant|mean|like|'d like|would like|'d rather|would rather|agree|choose|decide|wish|need)\b",
    r"\byour (call|choice|decision|answer|go|say|preference|pick)\b", r"\bup to you\b", r"\bover to you\b",
    r"\bwaiting (on|for) (you|your)\b", r"\bplease confirm\b", r"\bplease advise\b", r"\bwhich (one|do you|would you)\b",
    r"\b(shall|should|may|can) i\b", r"\bwant me to\b", r"\bwould you rather\b", r"\bor should i\b", r"\bor shall i\b",
    r"\bor do you\b", r"\bany (thoughts|objections|preference|preferences)\b", r"\bhow about\b", r"\bwhat about\b",
    r"\bis that (ok|okay|right|fine|correct|what you)\b",
]
QUESTION_OPTION = re.compile(r"^\s*([-*]\s*)?(\*\*)?(\(?[a-dA-D]\)|[A-D]:|option [a-d]\b)", re.I)


def unquoted(text: str) -> str:
    """The text without quotations, code and block quotes, so a phrase quoted as an example is not read as the reply's own words."""
    t = re.sub(r"```.*?```", " ", text or "", flags=re.S)
    t = re.sub(r"`[^`\n]*`", " ", t)
    t = re.sub(r'"[^"\n]{3,400}"', " ", t)
    t = re.sub(r"\u201c[^\u201d\n]{3,400}\u201d", " ", t)
    return "\n".join(l for l in t.splitlines() if not l.lstrip().startswith(">"))


def file_exists_anywhere(name: str) -> bool:
    """Is there a file with this name (or this path) anywhere the work could have put it?"""
    import tempfile
    base = os.path.basename(name)
    if os.path.isabs(name) and os.path.exists(name):
        return True
    roots = [project_dir(), Path("/mnt/user-data"), Path.home(), Path(tempfile.gettempdir())]
    seen = 0
    for root in roots:
        if not root.exists():
            continue
        for dp, dn, fn in os.walk(root):
            dn[:] = [d for d in dn if d not in (".git", "node_modules", "__pycache__", "proc", "sys")]
            seen += len(fn)
            if base in fn:
                return True
            if dp[len(str(root)):].count(os.sep) > 7 or seen > 80000:
                dn[:] = []
    return False


def questions_in(text: str) -> list:
    """Every sentence of the text that asks the owner something, in any of the ways English asks."""
    t = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text or "")
    t = re.sub(r"https?://\S+", " ", t)
    found, seen = [], set()
    for line in t.splitlines():
        if QUESTION_OPTION.match(line):
            s = line.strip()
            if s not in seen:
                seen.add(s)
                found.append(s)
        for s in re.split(r"(?<=[.!?])\s+", line):
            s = s.strip(" *_>#-\t")
            if len(s) <= 2 or s in seen:
                continue
            low = s.lower().strip(" \"'`(*_")
            asks = ("?" in s or re.match(QUESTION_WH + r"\b", low) or re.match(QUESTION_AUX + r"\s+" + QUESTION_SUBJ + r"\b", low)
                    or any(re.search(p, low) for p in QUESTION_INDIRECT))
            if asks:
                seen.add(s)
                found.append(s)
    return found


def settled_matches(text: str, settled: list) -> list:
    """The settled decisions a sentence touches. A decision has distinctive "words" (its subject) and helper words "also"
    (figures, directions). It is touched when at least one distinctive word is present and two words in all are."""
    out = []
    for e in settled:
        ws = [str(w) for w in e.get("words", []) if str(w).strip()]
        also = [str(w) for w in e.get("also", []) if str(w).strip()]
        if not ws:
            continue
        d = [w for w in ws if word_in(text, w)]
        a = [w for w in also if word_in(text, w)]
        if d and len(d) + len(a) >= 2:
            out.append((e, d + a))
    return out


def normalise_markdown(s: str) -> str:
    """Make the Drive copy and the repository copy comparable: drop markdown escapes and spacing."""
    s = s.replace("\r\n", "\n")
    s = re.sub(r"\\([#\-\.\*_\[\]\(\)!>+`~|])", r"\1", s)
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\s*\n\s*", "\n", s)
    return s.strip()


# ---------------------------------------------------------------- which "place" a search touched

READ_ONLY_CMD = re.compile(
    r"^\s*(ls|cat|head|tail|grep|egrep|rg|find|wc|sort|uniq|pwd|cd|echo|printf|which|stat|file|du|df|tree|diff|cmp|"
    r"sha256sum|shasum|md5sum|date|env|printenv|whoami|test|\[|true|false|sed\s+-n|awk|jq|column|basename|dirname|realpath|"
    r"gh\s+(pr|issue|run|repo|release|workflow|auth)\s+(list|view|diff|checks|status)\b|"
    r"gh\s+api\b(?!.*(\s-X\b|--method|\s-f\b|\s-F\b|--field|--raw-field|--input))|"
    r"git\s+(status|log|diff|show|ls-files|ls-remote|rev-list|cherry|merge-base|branch|rev-parse|remote|fetch|grep|blame|describe|shortlog|count-objects|config\s+--get)|"
    r"python3?\s+-[cI]*\s*['\"]?\s*(print|import json))",
    re.I,
)


def split_segments(cmd: str) -> list:
    return [s for s in re.split(r"&&|\|\||;|\||\n", cmd) if s.strip()]


def has_write_redirect(cmd: str) -> bool:
    c = re.sub(r"2>&1|>\s*/dev/null|2>\s*/dev/null|&>\s*/dev/null", "", cmd)
    return bool(re.search(r"(?<![<>=-])>>?(?!&)", c))


def bash_is_read_only(cmd: str) -> bool:
    if has_write_redirect(cmd):
        return False
    if re.search(r"\b(sed\s+-i|tee\b|find\b[^|;&]*(-delete|-exec|-ok)|xargs\b|dd\b|truncate\b|install\b|ln\b)", cmd):
        return False
    segs = split_segments(cmd)
    return bool(segs) and all(READ_ONLY_CMD.match(s) for s in segs)


SEARCH_TOOL_CMD = re.compile(r"""^\s*(cd\s+\S+\s*&&\s*)?python3?\s+(\"?\$CLAUDE_PROJECT_DIR\"?/|\./|\"?\$HOME\"?/\.mm-controls/|~/\.mm-controls/)?tools/search\.py(\s|$)""")


def is_search_tool(cmd: str) -> bool:
    return bool(SEARCH_TOOL_CMD.match(cmd or ""))


def places_for(tool_name: str, tool_input: dict) -> list:
    """Which of the named places did this tool call look into? (Only reading calls count.)"""
    t = tool_name or ""
    ti = tool_input or {}
    p = []
    if t in ("Read",):
        path = str(ti.get("file_path", ""))
        p += ["Files"]
        if re.search(r"(CLAUDE\.md|PROJECT-INSTRUCTIONS\.md)$", path):
            p += ["Project instructions"]
        if re.search(r"(^|/)records/", path):
            p += ["Records"]
        if re.search(r"(^|/)\.git/", path):
            p += ["Git history"]
    elif t in ("Glob", "Grep"):
        p += ["Files", "Working area (workspace)"]
        if re.search(r"(^|/)records(/|$)", str(ti.get("path", ""))):
            p += ["Records"]
    elif t == "Bash" and is_search_tool(str(ti.get("command", ""))):
        # tools/search.py reads every text file of the repository, the project instructions and the records folder
        p += ["Files", "Working area (workspace)", "Project instructions"]
        if (project_dir() / "records").is_dir():
            p += ["Records"]
    elif t == "Bash" or t.endswith("device_bash"):
        cmd = str(ti.get("command", ""))
        if bash_is_read_only(cmd) or re.search(r"\b(grep|rg|find|ls|cat|tree)\b", cmd):
            p += ["Files"] if t == "Bash" else ["Folders", "Connected Mac folders"]
            if t == "Bash":
                p += ["Working area (workspace)"]
            if re.search(r"git\s+(log|show|blame|grep|diff|describe)", cmd):
                p += ["Git history"]
            if re.search(r"(CLAUDE\.md|PROJECT-INSTRUCTIONS\.md)", cmd):
                p += ["Project instructions"]
    elif t.endswith("device_list_dir") or t.endswith("get_device_info"):
        p += ["Folders", "Connected Mac folders"]
    elif t == "Artifact":
        if str(ti.get("action", "publish")) in ("list", "read"):
            p += ["Artifacts"]
    elif t.startswith("mcp__Claude_Docs__") and re.search(r"__(query|read|guide)$", t):
        p += ["Claude docs"]
    elif t in ("mcp__claude_ai__conversation_search", "mcp__claude_ai__recent_chats", "mcp__claude_ai__read_conversation"):
        p += ["Chats"]
    elif t.startswith("mcp__Google_Drive__") and re.search(r"__(search_files|list_recent_files|read_file_content|get_file_metadata|get_file_permissions|download_file_content)$", t):
        p += ["Google Drive"]
        q = json.dumps(ti)
        if re.search(r"parentId|folder", q, re.I):
            p += ["Other Drive folders"]
    elif t.startswith("mcp__memory__memory_") and re.search(r"memory_(list|read)$", t):
        q = json.dumps(ti)
        p += ["Account memory and preferences", "Memory (project notes)"]
        if "/projects" in q:
            p += ["Project"]
    elif t in ("ListSkills", "SearchSkills", "ListPlugins", "SearchPlugins", "ListConnectors", "SearchMcpRegistry"):
        p += ["Skills and plugins"]
    elif t in ("WebFetch", "WebSearch"):
        q = json.dumps(ti)
        if re.search(r"montessorimentor", q, re.I):
            p += ["Live website"]
    elif t == "mcp__claude-code-remote__list_repos":
        p += ["Other GitHub repositories"]
    elif t.startswith("mcp__remote-devices__Claude_Browser__") or t.startswith("mcp__claude-in-chrome__"):
        q = json.dumps(ti)
        if re.search(r"montessorimentor", q, re.I):
            p += ["Live website"]
    seen = []
    for x in p:
        if x not in seen:
            seen.append(x)
    return seen


def targets_for(tool_name: str, tool_input: dict) -> list:
    """Short strings describing what a call touched, so replies can be checked against them."""
    ti = tool_input or {}
    out = [tool_name]
    for k in ("file_path", "path", "pattern", "query", "url", "command", "fileId", "title", "action", "prompt"):
        v = ti.get(k)
        if isinstance(v, str) and v:
            out.append(v[:300])
    for k in ("paths", "files"):
        v = ti.get(k)
        if isinstance(v, list):
            out += [str(x)[:200] for x in v[:20]]
    return out


def allow_silently():
    """No decision: the normal permission flow applies."""
    sys.exit(0)


DECISION_HOOK = None  # set by pre_tool.py: records every refusal and every click asked for, so the reviewer can see refused attempts


def decide(decision: str, reason: str):
    if DECISION_HOOK:
        try:
            DECISION_HOOK(decision, reason)
        except Exception:
            pass
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                              "permissionDecision": decision,
                                              "permissionDecisionReason": reason}}))
    sys.exit(0)


def deny(reason: str):
    decide("deny", reason)


def ask(reason: str):
    decide("ask", reason)


# ---------------------------------------------------------------- the decision register and the owner's words (owner's decision of 15 Oct 2026)
REGISTER_REL = "controls/decisions.json"
REGISTER_ABOUT = ("Every question Claude has put to the owner and every answer. Only the automatic checks write this file: a question is raised with "
                  "tools/ask.py and closed only by the owner's typed message ('Q4: 2'). While any question is open nothing is built, previewed, sent, "
                  "published or pushed.")
ANSWER_RE = re.compile(r"(?<![A-Za-z0-9])Q(\d+)\s*:\s*(\d+)(?!\d)", re.I)


def register_path() -> Path:
    return project_dir() / REGISTER_REL


def read_register() -> dict:
    try:
        d = json.loads(register_path().read_text(encoding="utf-8"))
        if isinstance(d, dict) and isinstance(d.get("questions"), list):
            return d
    except Exception:
        pass
    return {"version": 1, "about": REGISTER_ABOUT, "questions": []}


def write_register(d: dict) -> None:
    p = register_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, p)


def open_questions() -> list:
    return [q for q in read_register()["questions"] if q.get("status") == "open"]


def raise_question(text: str, options: list, session_id, turn: int) -> dict:
    d = read_register()
    nums = [int(re.sub(r"\D", "", str(q.get("id", "Q0"))) or 0) for q in d["questions"]]
    q = {"id": "Q" + str(max(nums + [0]) + 1), "text": text.strip(), "options": [o.strip() for o in options], "status": "open",
         "raised": time.strftime("%Y-%m-%d"), "raised_session": safe_id(session_id), "raised_turn": turn,
         "answer": None, "answer_text": None, "answered_words": None, "answered": None}
    d["questions"].append(q)
    write_register(d)
    return q


def close_from_prompt(prompt: str) -> list:
    """Only the owner's typed message can close a question, and only as 'Q<number>: <option number>' (decision C=1)."""
    d = read_register()
    closed = []
    for m in ANSWER_RE.finditer(prompt or ""):
        qid, n = "Q" + m.group(1), int(m.group(2))
        for q in d["questions"]:
            if q.get("id") == qid and q.get("status") == "open" and 1 <= n <= len(q.get("options", [])):
                q.update(status="answered", answer=n, answer_text=q["options"][n - 1], answered_words=prompt, answered=time.strftime("%Y-%m-%d"))
                closed.append(q)
    if closed:
        write_register(d)
    return closed


def register_ok_against(base_text: str, local_text: str) -> list:
    """The local register may differ from the approved one only by added questions and by answers to open ones."""
    problems = []
    try:
        base = {q["id"]: q for q in json.loads(base_text).get("questions", [])} if base_text.strip() else {}
        local = {q["id"]: q for q in json.loads(local_text).get("questions", [])} if local_text.strip() else {}
    except Exception:
        return ["the register is not readable"]
    for qid, b in base.items():
        l = local.get(qid)
        if l is None:
            problems.append(f"{qid} was removed")
            continue
        for k in ("text", "options", "raised"):
            if l.get(k) != b.get(k):
                problems.append(f"{qid} {k} was changed")
        if b.get("status") == "answered" and (l.get("status") != "answered" or l.get("answer") != b.get("answer") or l.get("answered_words") != b.get("answered_words")):
            problems.append(f"{qid} answer was changed")
    return problems


def append_prompt(session_id, turn: int, prompt: str) -> None:
    with open(state_dir(session_id) / "prompts.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"turn": turn, "prompt": prompt, "ts": round(time.time(), 1)}, ensure_ascii=False) + "\n")


def read_prompts(session_id) -> list:
    p = state_dir(session_id) / "prompts.jsonl"
    out = []
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except Exception:
                pass
    return out


# ---------------------------------------------------------------- the owner's orders (owner's decision of 15 Oct 2026, Q2: option 1)
ORDERS_REL = "controls/orders.json"
ORDERS_ABOUT = ("Every instruction the owner has typed, word for word, and the topics the owner has told Claude to drop. Only the automatic checks "
                "write this file (tools/order.py records the terms of a dropped topic, and only terms that are in the owner's own message). "
                "Each reply is compared with the owner's latest message and with these orders; a reply that mentions a dropped topic is refused.")


def orders_path() -> Path:
    return project_dir() / ORDERS_REL


def read_orders() -> dict:
    try:
        d = json.loads(orders_path().read_text(encoding="utf-8"))
        if isinstance(d, dict) and isinstance(d.get("orders"), list):
            return d
    except Exception:
        pass
    return {"version": 1, "about": ORDERS_ABOUT, "orders": []}


def write_orders(d: dict) -> None:
    p = orders_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, p)


def record_order(session_id, turn: int, words: str, drop: bool) -> dict:
    """Stores the owner's message word for word. A bare answer to a question ('Q2: 1') or a one-word go/push is not an order."""
    d = read_orders()
    text = (words or "").strip()[:2000]
    if not text or ANSWER_RE.fullmatch(text) or len(text.split()) < 2:
        return {}
    nums = [int(re.sub(r"\D", "", str(o.get("id", "O0"))) or 0) for o in d["orders"]]
    o = {"id": "O" + str(max(nums + [0]) + 1), "date": time.strftime("%Y-%m-%d"), "session": safe_id(session_id), "turn": turn,
         "words": text, "drop": bool(drop), "terms": [], "active": True}
    d["orders"].append(o)
    write_orders(d)
    return o


def drop_terms_ok(terms: list, owner_words: str) -> list:
    """Only words the owner actually typed may be recorded as a dropped topic (Claude cannot invent a ban or hide one)."""
    low = " " + normalise_quote(owner_words) + " "
    return [t for t in terms if t.strip() and " " + normalise_quote(t) + " " in low]


def add_drop_terms(session_id, turn: int, terms: list) -> dict:
    d = read_orders()
    for o in reversed(d["orders"]):
        if o.get("session") == safe_id(session_id) and o.get("turn") == turn and o.get("drop"):
            ok = drop_terms_ok(terms, o.get("words", ""))
            o["terms"] = sorted(set(o.get("terms", [])) | {t.strip() for t in ok})
            write_orders(d)
            return o
    return {}


def active_drop_terms() -> list:
    """[(term, order)] for every topic the owner has told Claude to drop."""
    return [(t, o) for o in read_orders()["orders"] if o.get("drop") and o.get("active", True) for t in o.get("terms", []) if t.strip()]


def dropped_mentions(text: str) -> list:
    low = " " + normalise_quote(text) + " "
    return [(t, o) for t, o in active_drop_terms() if " " + normalise_quote(t) + " " in low]


def canon_number(x) -> str:
    f = float(x)
    return str(int(f)) if f == int(f) else str(f)


def numbers_in(text: str) -> set:
    return {canon_number(n) for n in re.findall(r"(?<![\w.#])(\d+(?:\.\d+)?)", text or "")}


def figure_lines() -> dict:
    """START-HERE's numbered design-figure lines: {figure number: text}."""
    out = {}
    try:
        txt = (project_dir() / "controls" / "START-HERE.md").read_text(encoding="utf-8")
        sect = txt.split("## Design figures", 1)[1].split("Two kinds of page", 1)[0]
        for m in re.finditer(r"^(\d+)\. (.+)$", sect, re.M):
            out[int(m.group(1))] = m.group(2)
    except Exception:
        pass
    return out


def approved_numbers(session_id=None) -> set:
    """Numbers the owner has approved: the figures file, START-HERE's figure lines, answered questions, and (with a session) the owner's own messages."""
    nums = set()
    try:
        figs = json.loads((project_dir() / "controls" / "design-figures.json").read_text(encoding="utf-8"))
        for f in figs.get("figures", []):
            if f.get("expected") is not None:
                nums.add(canon_number(f["expected"]))
            nums |= numbers_in(f.get("text", ""))
    except Exception:
        pass
    for t in figure_lines().values():
        nums |= numbers_in(t)
    for q in read_register()["questions"]:
        if q.get("status") == "answered":
            nums |= numbers_in(q.get("answer_text", ""))
    if session_id:
        for p in read_prompts(session_id):
            nums |= numbers_in(p.get("prompt", ""))
    return nums
