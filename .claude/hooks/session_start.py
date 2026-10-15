"""SessionStart: checks the checks are intact, loads START-HERE and the project instructions into Claude's context."""
import json
import os
import subprocess
from pathlib import Path
from lib import *

ev = read_event()
sid = ev.get("session_id")
cfg = load_config()
root = project_dir()
st = load_state(sid)
problems, notes = [], []


def git(*args, timeout=25):
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, timeout=timeout)


# 1. Make the session id available to approved tools
envf = os.environ.get("CLAUDE_ENV_FILE")
if envf:
    with open(envf, "a", encoding="utf-8") as f:
        f.write(f"export CLAUDE_SESSION_ID={safe_id(sid)}\n")

# 2. Are the checks' own files the same as the version approved on GitHub?
watch = []
for pat in (".claude/hooks/*", ".claude/settings.json", "controls/*", "tools/*", "tests/*", ".github/workflows/*", ".github/CODEOWNERS", "CLAUDE.md"):
    for p in sorted(root.glob(pat)):
        if p.relative_to(root).as_posix() == REGISTER_REL:
            continue  # checked separately below: it may grow (added questions, answers) but not be rewritten
        if p.is_file() and "__pycache__" not in str(p) and p.suffix != ".pyc":
            watch.append(p.relative_to(root).as_posix())

compare_with = "origin/main"
try:
    r = git("fetch", "origin", "main", "--depth=1")
    if r.returncode != 0:
        compare_with = "HEAD"
        notes.append("Could not reach GitHub to compare; compared with the last saved version on this computer instead.")
except Exception:
    compare_with = "HEAD"
    notes.append("Could not reach GitHub to compare; compared with the last saved version on this computer instead.")

differs = []
for rp in watch:
    try:
        show = git("show", f"{compare_with}:{rp}")
        if show.returncode != 0:
            differs.append(rp + " (not in the approved version)")
            continue
        if show.stdout != (root / rp).read_bytes():
            differs.append(rp)
    except Exception:
        differs.append(rp + " (could not compare)")
if differs:
    problems.append("These control files differ from the approved version: " + ", ".join(differs[:8]))

try:
    base_reg = git("show", f"{compare_with}:{REGISTER_REL}")
    reg_problems = register_ok_against(base_reg.stdout.decode("utf-8") if base_reg.returncode == 0 else "",
                                       register_path().read_text(encoding="utf-8") if register_path().exists() else "")
    if reg_problems:
        problems.append("The decision register differs from the approved version by more than added questions and answers: " + "; ".join(reg_problems[:4]))
except Exception:
    problems.append("The decision register could not be compared with the approved version")

# 3. Are all the checks actually switched on, and nothing overriding them?
sj = root / ".claude" / "settings.json"
needed = ["SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "PostToolUseFailure", "Stop"]
try:
    hooks = json.loads(sj.read_text(encoding="utf-8")).get("hooks", {})
    for n in needed:
        if "run.sh" not in json.dumps(hooks.get(n, [])):
            problems.append(f"The {n} check is not switched on in .claude/settings.json")
except Exception:
    problems.append(".claude/settings.json is missing or unreadable")
local = root / ".claude" / "settings.local.json"
if local.exists():
    try:
        d = json.loads(local.read_text(encoding="utf-8"))
        if d.get("disableAllHooks") or d.get("hooks"):
            problems.append("settings.local.json tries to switch off or replace the checks")
    except Exception:
        problems.append("settings.local.json exists and is unreadable")
try:
    u = json.loads((Path.home() / ".claude" / "settings.json").read_text(encoding="utf-8"))
    if u.get("disableAllHooks"):
        notes.append("Your personal Claude settings have disableAllHooks on.")
except Exception:
    pass

st["tampered"] = bool(problems)
sh_path = root / cfg["start_here"]["copy_path"]
st["start_here_status"] = "loaded" if (sh_path.is_file() and sh_path.stat().st_size > 0) else "missing"
st["integrity_problems"] = problems
save_state(sid, st)
append_log(sid, {"turn": st.get("turn", 0), "event": "session_start", "source": ev.get("source"),
                 "problems": problems, "notes": notes})

# 4. What Claude is told at the start
parts = []
if problems:
    parts.append("INTEGRITY FAILURE - STOP. Tell the owner in plain English before anything else:\n- " + "\n- ".join(problems)
                 + "\nNo change to anything is allowed until the owner restores the approved version.")
else:
    parts.append("The automatic checks are intact and switched on." + (" " + " ".join(notes) if notes else ""))
_oq = open_questions()
if _oq:
    parts.append("OPEN QUESTIONS waiting for the owner's answer (nothing that depends on them may be built, previewed, sent, published or pushed): "
                 + " | ".join(f"{q['id']}: {q['text']}" for q in _oq))
parts.append("START-HERE.md is loaded below. It is the master copy and lives in this repository (controls/START-HERE.md). It is not kept in Google Drive.")
for rel_path in cfg["context_files"]:
    p = root / rel_path
    if p.exists():
        parts.append(f"===== {rel_path} =====\n" + p.read_text(encoding="utf-8"))
text = "\n\n".join(parts)
if len(text) > 9800:
    text = text[:9800] + "\n[cut: read the rest in controls/]"
print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}))
sys.exit(0)
