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
    return json.loads(raw) if raw.strip() else {}


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


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


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
    r"git\s+(status|log|diff|show|ls-files|branch|rev-parse|remote|fetch|grep|blame|describe|shortlog|count-objects|config\s+--get)|"
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
        if re.search(r"(^|/)\.git/", path):
            p += ["Git history"]
    elif t in ("Glob", "Grep"):
        p += ["Files", "Working area (workspace)"]
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


def decide(decision: str, reason: str):
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                              "permissionDecision": decision,
                                              "permissionDecisionReason": reason}}))
    sys.exit(0)


def deny(reason: str):
    decide("deny", reason)


def ask(reason: str):
    decide("ask", reason)
