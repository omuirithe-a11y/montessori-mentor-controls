"""PreToolUse: runs BEFORE every action. Can refuse (deny) or force a click from the owner (ask).
Never returns "allow": a neutral action simply goes through the normal permission flow."""
import os
import re
import shlex
from pathlib import Path
from lib import *

ev = read_event()
sid = ev.get("session_id")
cfg = load_config()
st = load_state(sid)
tool = ev.get("tool_name", "") or ""
ti = ev.get("tool_input") or {}
turn = int(st.get("turn", 0))
root = project_dir()
HOME = str(Path.home())

import lib as _lib  # noqa: E402


def _log_decision(decision, reason):
    """Every refusal and every click asked for goes in the log, so a refused attempt is visible to the reviewer and to the owner."""
    append_log(sid, {"turn": turn, "event": "decision", "tool": tool, "decision": decision,
                     "targets": targets_for(tool, ti)[:3], "reason": str(reason)[:200]})


_lib.DECISION_HOOK = _log_decision

OPEN_Q = open_questions()


def deny_if_open(what):
    """While any question is open nothing is built, previewed, sent, published or pushed (owner's decision of 15 Oct 2026)."""
    if OPEN_Q:
        q = OPEN_Q[0]
        deny(f"Not allowed: {what} while a question is open. {q['id']} is still open: {q['text']} Wait for the owner's answer: the owner answers by typing "
             f"{q['id']}: <option number>. Open now: " + ", ".join(x["id"] for x in OPEN_Q) + ".")


# ------------------------------------------------------------------ path helpers
def norm(path: str) -> str:
    p = os.path.expanduser(str(path))
    if not os.path.isabs(p):
        p = os.path.join(str(root), p)
    return os.path.normpath(p)


def rel(path: str) -> str:
    p = norm(path)
    r = str(root)
    return p[len(r) + 1:] if p.startswith(r + os.sep) else p


def inside_root(path: str) -> bool:
    return norm(path).startswith(str(root) + os.sep)


def ext(path: str) -> str:
    return os.path.splitext(str(path).lower())[1]


def is_locked(path: str) -> bool:
    p = norm(path)
    r = rel(path)
    if r == REGISTER_REL or any(r.startswith(x) for x in cfg["locked_paths"]):
        return True
    if "/.claude/settings" in p or p.startswith(os.path.join(HOME, ".claude") + os.sep):
        return True
    return False


def is_control(path: str) -> bool:
    r = rel(path)
    return inside_root(path) and any(r == x or r.startswith(x) for x in cfg["protected_control_paths"])


def in_work_copy_folder(path: str) -> bool:
    segs = [s.lower() for s in norm(path).split(os.sep)[:-1]]
    return any(s in cfg["work_copy_folder_names"] for s in segs)


def is_original(path: str) -> bool:
    return ext(path) in cfg["original_extensions"] and not in_work_copy_folder(path)


def repo_violations() -> list:
    out = []
    try:
        import subprocess
        names = set(subprocess.run(["git", "-C", str(root), "ls-files"], capture_output=True, text=True).stdout.split("\n"))
        names |= set(subprocess.run(["git", "-C", str(root), "diff", "--cached", "--name-only"], capture_output=True, text=True).stdout.split("\n"))
    except Exception:
        names = set()
    for n in sorted(x for x in names if x):
        f = root / n
        if ext(n) in cfg["forbidden_extensions"]:
            out.append(f"{n}: file type not allowed in this repository")
        elif f.exists() and f.is_file() and f.stat().st_size > cfg["max_file_bytes"]:
            out.append(f"{n}: file is {f.stat().st_size // 1000} KB, the limit is {cfg['max_file_bytes'] // 1000} KB")
    total = 0
    g = root / ".git"
    if g.exists():
        for dp, _, fs in os.walk(g):
            for x in fs:
                try:
                    total += os.path.getsize(os.path.join(dp, x))
                except OSError:
                    pass
    if total > cfg["repo_block_bytes"]:
        out.append(f"repository is {total // 1000000} MB, the limit is {cfg['repo_block_bytes'] // 1000000} MB")
    return out


# ------------------------------------------------------------------ the owner's permissions
def go_given() -> bool:
    return st.get("go_turn") == turn and turn > 0


def push_words_given() -> bool:
    return st.get("push_ok_turn") == turn and turn > 0


# ------------------------------------------------------------------ gates for any change
def gate_for_change(control=False):
    """Search before acting, START-HERE present, controls intact."""
    if st.get("tampered") and not control:
        deny("Not allowed: the automatic checks found that their own files were changed. "
             "Stop and tell the owner in plain English. Nothing can be changed until the owner restores them.")
    sh_path = project_dir() / cfg["start_here"]["copy_path"]
    if not (sh_path.is_file() and sh_path.stat().st_size > 0):
        deny("Not allowed: START-HERE (controls/START-HERE.md) is missing or empty. "
             "Tell the owner in plain English. Nothing can be changed until it is restored.")
    declared = read_declared(sid)
    log = read_log(sid)
    scope = cfg.get("search_scope", "turn")
    use = (lambda r: r.get("turn") == turn) if scope == "turn" else (lambda r: True)
    covered = set()
    for r in log:
        if r.get("event") == "tool" and r.get("ok") and use(r):
            covered.update(r.get("places", []))
    for d in declared:
        if use(d):
            covered.add(d.get("place"))
    missing = [p for p in cfg["required_places"] if p not in covered]
    if missing:
        deny("Not allowed yet: before changing anything, these places have not been searched in this "
             + ("reply" if scope == "turn" else "session") + ": " + "; ".join(missing)
             + ". Search them now (several at once). If one is not offered in this session, record it with: "
             "python3 tools/declare.py \"<place>\" \"<reason>\"  (reasons: " + "; ".join(cfg["unavailable_reasons_allowed"]) + ").")


def change(reason_for_owner: str, control=False):
    gate_for_change(control)
    ask(reason_for_owner)


# ------------------------------------------------------------------ preview gate
def receipt_ok(path: str) -> bool:
    f = Path(norm(path))
    if not f.exists():
        return True  # nothing to check; the tool itself will fail
    h = hashlib.sha256(f.read_bytes()).hexdigest()
    return (root / ".session" / "receipts" / f"{h}.json").exists()


def preview_paths(paths) -> list:
    return [p for p in paths if re.search(r"(^|/)pages?/", rel(p)) and ext(p) in (".html", ".htm")]


# ------------------------------------------------------------------ file tools
if tool in ("Edit", "Write", "NotebookEdit"):
    path = ti.get("file_path") or ti.get("notebook_path") or ""
    if is_locked(path):
        deny("Not allowed: this file belongs to the automatic checks and cannot be changed by Claude.")
    if is_original(path):
        deny("Not allowed: this is one of your originals (Word, PDF or photo). Originals are never edited. "
             "Work on a copy in a folder named work, copy or preview.")
    if re.search(cfg.get("page_dir_regex", "(^|/)pages?/"), rel(path)):
        deny_if_open("writing or changing a page file")
    if inside_root(path):
        if ext(path) in cfg["forbidden_extensions"]:
            deny("Not allowed: Word files, PDFs, photos, zips and other large file types cannot be saved in this repository.")
        content = ti.get("content") or ti.get("new_string") or ""
        if len(str(content).encode("utf-8")) > cfg["max_file_bytes"]:
            deny("Not allowed: this is larger than the " + str(cfg["max_file_bytes"] // 1000) + " KB limit for one file in this repository.")
    if is_control(path):
        change("Claude wants to change one of the automatic checks (" + rel(path) + "). Only approve if YOU asked for this change.", control=True)
    gate_for_change()
    if inside_root(path) or in_work_copy_folder(path):
        # An ordinary file in the repository, or in a work, copy or preview folder: no decision here.
        # Claude Code's own permission prompt decides (changed 14 Oct 2026 at the owner's request).
        allow_silently()
    ask("Claude wants to change the file " + rel(path) + ", which is outside the repository and outside any work, copy or preview folder. Approve only if you asked for this.")

# ------------------------------------------------------------------ shell commands
if tool == "Bash" or tool.endswith("device_bash"):
    cmd = str(ti.get("command", ""))
    SANCTIONED = re.compile(
        r"""^\s*python3?\s+(\"?\$CLAUDE_PROJECT_DIR\"?/|\./|\"?\$HOME\"?/\.mm-controls/|~/\.mm-controls/)?(tools/(declare|search|ask|brief|preview_gate|measure_spacing|check_wording|size_alarm)\.py|tests/prove_it_bites\.py)(\s+[^;&|><`$]*)?\s*$""")
    if tool == "Bash" and SANCTIONED.match(cmd):
        if re.search(r"tools/(preview_gate|brief)\.py", cmd):
            deny_if_open("issuing a preview receipt")
        allow_silently()

    if re.search(r"(--no-verify|core\.hooksPath|disableAllHooks|dangerously-skip-permissions|HOOK_PYTHON|CLAUDE_PROJECT_DIR\s*=)", cmd):
        deny("Not allowed: this tries to switch off or get around the automatic checks.")

    read_only = bash_is_read_only(cmd)

    locked_ref = re.search(r"(\.session/|controls/decisions\.json|settings\.local\.json|(~|\$HOME|/root|/home/[^/\s]+|/Users/[^/\s]+)/\.claude)", cmd)
    if locked_ref and not read_only:
        deny("Not allowed: this would change the automatic checks' own records or settings.")

    pub = re.search(cfg["publish_bash_regex"], cmd) or (
        re.search(cfg["hostinger_words_regex"], cmd) and re.search(cfg["hostinger_with_regex"], cmd))
    if pub and not read_only:
        deny_if_open("going live")
        if not go_given():
            deny("Not allowed: nothing goes live or gets uploaded without your \"go\". "
                 "Ask the owner; the owner must type: go")
        ask("Claude wants to put something on the live website or upload it. You typed go. Approve only if this is what you meant.")

    # originals: anything that rewrites, moves or deletes one
    if not read_only:
        for seg in split_segments(cmd):
            try:
                toks = shlex.split(seg)
            except ValueError:
                toks = seg.split()
            if not toks:
                continue
            verb = os.path.basename(toks[0])
            paths = [t for t in toks[1:] if not t.startswith("-") and ext(t) in cfg["original_extensions"]]
            if verb == "cp":
                nonflag = [t for t in toks[1:] if not t.startswith("-")]
                dest = nonflag[-1] if nonflag else ""
                if ext(dest) in cfg["original_extensions"] and not in_work_copy_folder(dest):
                    deny("Not allowed: this would overwrite one of your originals.")
            elif verb in ("rm", "mv", "sed", "tee", "truncate", "chmod", "unzip", "python", "python3", "perl", "dd", "shred") and paths:
                if any(not in_work_copy_folder(p) for p in paths):
                    deny("Not allowed: originals (Word, PDF, photos) are never edited, moved or deleted. Work on a copy in a folder named work, copy or preview.")
            if re.search(r">\s*\S+", seg):
                for m in re.findall(r">>?\s*([^\s;&|]+)", seg):
                    if is_original(m):
                        deny("Not allowed: this would overwrite one of your originals.")

    if re.search(r"\bgit\s+(commit|add|push)\b", cmd):
        v = repo_violations()
        if v:
            deny("Not allowed: the repository rules are broken: " + " | ".join(v[:6]))
    if re.search(r"\bgit\s+push\b", cmd):
        deny_if_open("pushing to GitHub")
        if not push_words_given():
            deny("Not allowed: saving to GitHub only happens when you ask for it by name (say push, commit or GitHub). "
                 "\"Save this\" means a download link, never GitHub.")
        # Owner's decision of 15 Oct 2026: while the integrity warning is on (the branch's own check changes are not merged yet), a plain push of a
        # branch other than main is still allowed, with the owner's click. GitHub's lock on main (pull request, the owner's review, the required
        # checks) is what protects the approved version. Anything else (main, force, delete, several refs) is still refused.
        m_push = re.match(r"^\s*git\s+push\s+(?:-u\s+|--set-upstream\s+)?origin\s+([A-Za-z0-9][A-Za-z0-9._/-]*)\s*$", cmd)
        plain_branch_push = bool(m_push) and m_push.group(1) not in ("main", "master", "HEAD")
        change("Claude wants to send changes to GitHub. You asked for GitHub in your last message. Approve only if that is what you meant.",
               control=plain_branch_push)

    if read_only:
        allow_silently()
    ctrl_ref = re.search(r"(\.claude/|controls/|tools/|tests/|\.github/|CLAUDE\.md)", cmd)
    if ctrl_ref:
        change("Claude wants to run a command that changes the automatic checks. Only approve if YOU asked for this change.", control=True)
    change("Claude wants to run a command that changes files. Approve only if you asked for this.")

# ------------------------------------------------------------------ everything else (connectors and special tools)
if re.match(cfg["gate_exempt_tools_regex"], tool):
    allow_silently()

last = tool.split("__")[-1]

if re.search(cfg["publish_tool_name_regex"], tool):
    deny_if_open("going live")
    if not go_given():
        deny("Not allowed: nothing goes live or gets uploaded without your \"go\". The owner must type: go")
    ask("Claude wants to put something on the live website. You typed go. Approve only if this is what you meant.")

if tool.startswith("mcp__Google_Drive__"):
    if last in ("update_file", "trash_file", "share_file"):
        deny("Not allowed: Claude does not change, delete or share your Google Drive files. Originals are never edited.")
    if last in ("create_file", "copy_file"):
        change("Claude wants to add a new file to your Google Drive. Approve only if you asked for this.")
    allow_silently()

if tool.endswith("device_commit_files"):
    for f in ti.get("files", []) or []:
        dp = str(f.get("devicePath", ""))
        if is_original(dp):
            deny("Not allowed: this would overwrite one of your originals on your computer.")
    change("Claude wants to write files onto your computer. Approve only if you asked for this.")

if tool.endswith("device_request_delete_permission"):
    ask("Claude is asking permission to delete files on your computer. Approve only if you asked for this.")

if tool in ("SendUserFile", "Artifact"):
    if tool == "SendUserFile" or str(ti.get("action", "publish")) == "publish":
        deny_if_open("sending a file or publishing a page")
    paths = []
    if tool == "SendUserFile":
        paths = [str(x) for x in ti.get("files", []) or []]
    else:
        fp = ti.get("file_path")
        if fp and str(ti.get("action", "publish")) == "publish":
            paths = [str(fp)]
    for p in preview_paths(paths):
        if not receipt_ok(p):
            deny("Not allowed: this page has not passed the spacing and wording checks. Run: python3 tools/preview_gate.py <page.html> <source-text-file>")
    if tool == "Artifact" and str(ti.get("action", "publish")) in ("list", "read", "open", "quickstart"):
        allow_silently()
    if tool == "Artifact":
        change("Claude wants to publish or change a page that is hosted on claude.ai. Approve only if you asked for this.")
    allow_silently()

if tool.startswith("mcp__") or tool in ("Agent", "CronCreate", "CronDelete", "mcp__claude-code-remote__create_trigger"):
    if re.match(r"^(get|list|read|search|query|find|fetch|describe|preview|check|current|approximate|display|show|recent|conversation|image_search|computer_screenshot|computer_zoom|computer_list|tabs_context|read_page)", last):
        allow_silently()
    if re.search(cfg["change_tool_name_regex"], last):
        change("Claude wants to use \"" + tool + "\", which changes something outside this chat. Approve only if you asked for this.")

allow_silently()
