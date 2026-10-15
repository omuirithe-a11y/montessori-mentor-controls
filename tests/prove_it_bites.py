"""Proves the automatic checks still bite: tries every forbidden action on purpose, on a throwaway copy of the repository,
and confirms each one is blocked (and that normal safe actions are not). Exit 0 only if every scenario behaves as expected.
Usage: python3 tests/prove_it_bites.py"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RESULTS = []
TMP = None


def sh(*a, cwd=None, env=None, input=None):
    return subprocess.run(a, cwd=cwd, env=env, input=input, capture_output=True, text=True)


def build_copy():
    d = Path(tempfile.mkdtemp(prefix="bites_"))
    for item in REPO.iterdir():
        if item.name in (".git", ".session", "__pycache__"):
            continue
        if item.is_dir():
            shutil.copytree(item, d / item.name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        else:
            shutil.copy2(item, d / item.name)
    (d / ".claude").mkdir(exist_ok=True)
    shutil.copy2(d / "controls" / "settings.armed.json", d / ".claude" / "settings.json")
    sh("git", "init", "-q", "-b", "main", cwd=d)
    sh("git", "config", "user.email", "t@t", cwd=d)
    sh("git", "config", "user.name", "t", cwd=d)
    sh("git", "add", "-A", cwd=d)
    sh("git", "commit", "-q", "-m", "test copy", cwd=d)
    return d


def hook(name, event, env_extra=None):
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(TMP))
    env.pop("HOOK_PYTHON", None)
    env["MM_REVIEWER_DISABLE"] = "1"  # the reviewer (a second model) is off in the tests unless a test turns it on with a fake one
    env.update(env_extra or {})
    r = sh("sh", str(TMP / ".claude" / "hooks" / "run.sh"), name, env=env, input=json.dumps(event))
    out = None
    if r.stdout.strip():
        try:
            out = json.loads(r.stdout.strip().splitlines()[-1])
        except Exception:
            out = {"raw": r.stdout}
    return r.returncode, out, r.stderr


def decision(out):
    return (out or {}).get("hookSpecificOutput", {}).get("permissionDecision")


def reason(out):
    return (out or {}).get("hookSpecificOutput", {}).get("permissionDecisionReason", "")


class Sess:
    def __init__(self, prompt="Hi."):
        self.sid = "t" + uuid.uuid4().hex[:8]
        self.base = {"session_id": self.sid}
        hook("user_prompt", dict(self.base, hook_event_name="UserPromptSubmit", prompt=prompt))

    def prompt(self, text):
        return hook("user_prompt", dict(self.base, hook_event_name="UserPromptSubmit", prompt=text))

    def env(self):
        return dict(os.environ, CLAUDE_PROJECT_DIR=str(TMP), CLAUDE_SESSION_ID=self.sid)

    def words(self):
        try:
            return json.loads((TMP / ".session" / self.sid / "state.json").read_text()).get("search_content", [])
        except Exception:
            return []

    def search(self, *args):
        """Run the search tool as Claude would, and log the call as the PostToolUse check would."""
        r = sh("python3", str(TMP / "tools" / "search.py"), *args, env=self.env())
        self.post("Bash", {"command": "python3 tools/search.py" + ("".join(f' "{a}"' for a in args))}, "x")
        return r

    def drive(self, word=None):
        w = word or (self.words() or ["x"])[0]
        self.post("mcp__Google_Drive__search_files", {"query": f"fullText contains '{w}'"}, "x")

    def post(self, tool, ti, resp="ok", fail=False):
        return hook("post_tool", dict(self.base, hook_event_name="PostToolUseFailure" if fail else "PostToolUse",
                                      tool_name=tool, tool_input=ti, tool_response=resp))

    def pre(self, tool, ti):
        rc, out, err = hook("pre_tool", dict(self.base, hook_event_name="PreToolUse", tool_name=tool, tool_input=ti))
        return rc, out, err

    def stop(self, msg):
        return hook("stop", dict(self.base, hook_event_name="Stop", last_assistant_message=msg))

    def satisfy(self, skip=(), search=True, drive_word=None):
        calls = [
            ("Read", {"file_path": str(TMP / "controls" / "PROJECT-INSTRUCTIONS.md")}, "x"),
            ("Glob", {"pattern": "**/*.md"}, "x"),
            ("Artifact", {"action": "list"}, "x"),
            ("mcp__Claude_Docs__query", {"q": "x"}, "x"),
            ("mcp__claude_ai__conversation_search", {"query": "x"}, "x"),
            ("mcp__memory__memory_read", {"path": "/projects/x.md"}, "x"),
            ("ListSkills", {}, "x"),
            ("mcp__remote-devices__device_list_dir", {"path": "/x"}, "x"),
        ]
        for t, ti, resp in calls:
            if t not in skip:
                self.post(t, ti, resp)
        if search:
            self.search()
        if "mcp__Google_Drive__search_files" not in skip:
            self.drive(drive_word)


def expect(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))


def reason_of(out):
    return str((out or {}).get("reason", ""))


def run():
    global TMP
    TMP = build_copy()
    work = str(TMP)

    # ---- 1. protection of originals and the checks' own files
    s = Sess(); s.satisfy()
    expect("editing a Word original is refused", decision(s.pre("Edit", {"file_path": "/x/essay.docx"})[1]) == "deny")
    expect("overwriting a PDF original in the repo is refused", decision(s.pre("Write", {"file_path": work + "/a.pdf", "content": "x"})[1]) == "deny")
    expect("saving a photo into the repository is refused", decision(s.pre("Write", {"file_path": work + "/photo.jpg", "content": "x"})[1]) == "deny")
    expect("a file over the size limit is refused", decision(s.pre("Write", {"file_path": work + "/big.txt", "content": "x" * 1_100_000})[1]) == "deny")
    expect("changing the search log or state is refused", decision(s.pre("Write", {"file_path": work + "/.session/x/log.jsonl", "content": "x"})[1]) == "deny")
    expect("switching hooks off via settings.local.json is refused", decision(s.pre("Write", {"file_path": work + "/.claude/settings.local.json", "content": "{}"})[1]) == "deny")
    expect("changing personal Claude settings is refused", decision(s.pre("Write", {"file_path": str(Path.home() / ".claude" / "settings.json"), "content": "{}"})[1]) == "deny")
    expect("changing a check file needs the owner's click", decision(s.pre("Edit", {"file_path": work + "/.claude/hooks/stop.py", "new_string": "x"})[1]) == "ask")
    expect("a shell command that changes a check file needs a click", decision(s.pre("Bash", {"command": "sed -i s/a/b/ .claude/hooks/stop.py"})[1]) == "ask")
    expect("a shell command that edits the logs is refused", decision(s.pre("Bash", {"command": "echo x > .session/a/log.jsonl"})[1]) == "deny")
    expect("--no-verify is refused", decision(s.pre("Bash", {"command": "git commit --no-verify -m x"})[1]) == "deny")
    expect("changing the hooks path is refused", decision(s.pre("Bash", {"command": "git config core.hooksPath /tmp/x"})[1]) == "deny")
    expect("deleting a Word original by shell is refused", decision(s.pre("Bash", {"command": "rm essay.docx"})[1]) == "deny")
    expect("overwriting an original by copy is refused", decision(s.pre("Bash", {"command": "cp new.txt essay.docx"})[1]) == "deny")
    expect("copying an original into a work folder is not refused", decision(s.pre("Bash", {"command": "cp essay.docx work/essay.docx"})[1]) != "deny")
    expect("Google Drive files cannot be trashed", decision(s.pre("mcp__Google_Drive__trash_file", {"fileId": "x"})[1]) == "deny")
    expect("Google Drive files cannot be updated", decision(s.pre("mcp__Google_Drive__update_file", {"fileId": "x"})[1]) == "deny")
    expect("Google Drive files cannot be shared", decision(s.pre("mcp__Google_Drive__share_file", {"fileId": "x"})[1]) == "deny")
    expect("writing an original onto the owner's computer is refused", decision(s.pre("mcp__remote-devices__device_commit_files", {"files": [{"devicePath": "/Users/a/Docs/essay.docx"}]})[1]) == "deny")

    # ---- 2. nothing goes live without "go"
    s = Sess(); s.satisfy()
    expect("uploading to the live site is refused without go", decision(s.pre("Bash", {"command": "scp page.html me@host:/public_html/"})[1]) == "deny")
    expect("a Hostinger tool is refused without go", decision(s.pre("mcp__hostinger__upload_site", {})[1]) == "deny")
    s.prompt("go")
    expect("after the owner types go, upload still needs a click", decision(s.pre("Bash", {"command": "scp page.html me@host:/public_html/"})[1]) == "ask")
    s.prompt("keep going please")
    expect("go does not carry over to the next message", decision(s.pre("Bash", {"command": "scp page.html me@host:/public_html/"})[1]) == "deny")

    # ---- 3. "save this" never means GitHub
    s = Sess("save this"); s.satisfy()
    expect("pushing to GitHub is refused when the owner only said save this", decision(s.pre("Bash", {"command": "git push origin main"})[1]) == "deny")
    s.prompt("please push it to GitHub"); s.satisfy()
    expect("pushing after the owner names GitHub needs a click", decision(s.pre("Bash", {"command": "git push origin main"})[1]) == "ask")
    (TMP / "oops.pdf").write_bytes(b"x")
    sh("git", "add", "oops.pdf", cwd=TMP)
    expect("committing a PDF is refused", decision(s.pre("Bash", {"command": "git commit -m x"})[1]) == "deny")
    sh("git", "rm", "-q", "-f", "oops.pdf", cwd=TMP)

    # ---- 4. search before acting
    s = Sess()
    rc, out, _ = s.pre("Edit", {"file_path": work + "/pages/x.html", "new_string": "x"})
    expect("changing a page with nothing searched is refused and names the places", decision(out) == "deny" and "Artifacts" in reason(out))
    s.satisfy()
    expect("after every place is searched, an ordinary page edit is left to Claude Code's own prompt", decision(s.pre("Edit", {"file_path": work + "/pages/x.html", "new_string": "x"})[1]) is None)
    expect("an edit to a page in the repository gives no decision", decision(s.pre("Edit", {"file_path": work + "/pages/x.html", "new_string": "x"})[1]) is None)
    expect("an edit to a file in a work folder gives no decision", decision(s.pre("Edit", {"file_path": "/x/work/page.html", "new_string": "x"})[1]) is None)
    expect("writing a file outside the repository and any work folder needs a click", decision(s.pre("Write", {"file_path": "/x/notes.txt", "content": "x"})[1]) == "ask")
    expect("editing a control file still needs a click", decision(s.pre("Edit", {"file_path": work + "/controls/config.json", "new_string": "x"})[1]) == "ask")
    s.prompt("next question")
    expect("search must be repeated in the next reply", decision(s.pre("Edit", {"file_path": work + "/pages/x.html", "new_string": "x"})[1]) == "deny")
    expect("read-only commands pass untouched", s.pre("Bash", {"command": "ls -la"})[1] is None)
    expect("searching is never blocked", s.pre("Grep", {"pattern": "x"})[1] is None)

    # ---- 5. START-HERE lives in the repository: if it is missing, nothing can change
    s = Sess(); s.satisfy()
    sh_file = TMP / "controls" / "START-HERE.md"
    saved = sh_file.read_text()
    sh_file.unlink()
    out = s.pre("Edit", {"file_path": work + "/pages/x.html", "new_string": "x"})[1]
    expect("with START-HERE missing, every change is refused", decision(out) == "deny" and "START-HERE" in reason(out))
    sh_file.write_text(saved)
    expect("with START-HERE restored, an ordinary page edit goes through again", decision(s.pre("Edit", {"file_path": work + "/pages/x.html", "new_string": "x"})[1]) is None)

    # ---- 6. Stop: the reply must report truthfully
    s = Sess(); s.satisfy(skip=("ListSkills",))
    places = "Files; Artifacts; Claude docs; Chats; Project; Project instructions; Memory (project notes); Account memory and preferences; Skills and plugins; Folders; Working area (workspace); Google Drive"
    rc, out, _ = s.stop("Here is the answer.")
    expect("a reply with no search report is rejected", (out or {}).get("decision") == "block")
    # Skills and plugins isn't covered here, so it must be declared
    good = f"Answer.\nSearched: Files; Artifacts; Claude docs; Chats; Project; Project instructions; Memory (project notes); Account memory and preferences; Folders; Working area (workspace); Google Drive\nCouldn't search: Skills and plugins - not offered in this session"
    rc, out, _ = s.stop(good)
    expect("a place claimed unavailable but not recorded is rejected", (out or {}).get("decision") == "block")
    sh("python3", str(TMP / "tools" / "declare.py"), "Skills and plugins", "not offered in this session", env=s.env())
    rc, out, _ = s.stop(good)
    expect("a truthful report is accepted", (out or {}).get("decision") != "block" and rc == 0, reason_of(out))
    s2 = Sess()
    rc, out, _ = s2.stop(f"Answer.\nSearched: {places}\nCouldn't search: none")
    expect("claiming searches that are not in the log is rejected", (out or {}).get("decision") == "block")
    r = sh("python3", str(TMP / "tools" / "declare.py"), "Files", "not offered in this session", env=s.env())
    expect("a place already searched cannot be declared unavailable", r.returncode != 0)
    rc, out, _ = s.stop(good.replace("Answer.", "I checked it and it is done."))
    expect("saying checked/done without 'Looked at' is rejected", (out or {}).get("decision") == "block")
    rc, out, _ = s.stop(good.replace("Answer.", "I checked it.") + "\nLooked at: the moon; a unicorn")
    expect("'Looked at' naming things never touched is rejected", (out or {}).get("decision") == "block")
    rc, out, _ = s.stop(good.replace("Answer.", "I checked it.") + "\nLooked at: PROJECT-INSTRUCTIONS.md")
    expect("'Looked at' naming something really read is accepted", (out or {}).get("decision") != "block")
    s3 = Sess()
    last = None
    for _ in range(61):
        rc, last, _ = s3.stop("no footer")
    expect("after 60 tries a reply is still not let through; it is told to give a best-result report", (last or {}).get("decision") == "block" and "Best result so far" in str((last or {}).get("reason", "")))
    rc, last, _ = s3.stop("Best result so far: none yet.\nStill not searched or found: everything.\nSearched: none\nCouldn't search: none")
    expect("a best-result report ends the loop and the owner is told", "systemMessage" in (last or {}))
    s4 = Sess()
    rc, out, _ = s4.stop("The gate stopped me, so I stop here.")
    expect("a block message tells Claude to keep going and names the next step", (out or {}).get("decision") == "block" and "KEEP GOING" in reason_of(out) and "NEXT STEP" in reason_of(out))
    expect("'a check stopped me' is refused as an ending", "stopped" in reason_of(out) and "carry on" in reason_of(out))

    # ---- 6a. the owner's decisions of 15 Oct 2026: quotations, file claims, read-only lookups, one-command declare, the reviewer
    s5 = Sess(); s5.satisfy()
    foot_all = f"\nSearched: {places}\nCouldn't search: none"
    rc, out, _ = s5.stop('An example of a refused ending is "the gate stopped me, so I stop here" and nothing else.' + foot_all)
    expect("a phrase inside quotation marks is not read as the reply's own words", (out or {}).get("decision") != "block", reason_of(out))
    rc, out, _ = s5.stop("The gate stopped me, so I stop here." + foot_all)
    expect("the same phrase used for real is still refused", (out or {}).get("decision") == "block")
    s6 = Sess(); s6.satisfy()
    foot_l = foot_all + "\nLooked at: PROJECT-INSTRUCTIONS.md"
    rc, out, _ = s6.stop("I created Missing-Report-xyz.docx for you." + foot_l)
    expect("a reply saying a file was made is refused when no such file exists", (out or {}).get("decision") == "block" and "Missing-Report-xyz.docx" in reason_of(out))
    (TMP / "Real-Report-xyz.docx").write_bytes(b"x")
    rc, out, _ = s6.stop("I created Real-Report-xyz.docx for you." + foot_l)
    expect("the same claim is accepted when the file exists", (out or {}).get("decision") != "block", reason_of(out))
    rc, out, _ = s6.stop("I did not create Missing-Report-xyz.docx." + foot_l)
    expect("saying a file was NOT made is not refused", (out or {}).get("decision") != "block", reason_of(out))
    s7 = Sess()
    expect("a read-only GitHub lookup is allowed", decision(s7.pre("Bash", {"command": "gh pr list --repo a/b"})[1]) is None)
    expect("a read-only GitHub API read is allowed", decision(s7.pre("Bash", {"command": "gh api repos/a/b/pulls/1"})[1]) is None)
    expect("a GitHub write is still gated", decision(s7.pre("Bash", {"command": "gh api repos/a/b/issues -X POST"})[1]) == "deny")
    s8 = Sess()
    r = sh("python3", str(TMP / "tools" / "declare.py"), "--cloud-defaults", env=s8.env())
    expect("one command records the five places a cloud session never offers", r.returncode == 0 and r.stdout.count("Recorded") == 5, r.stdout + r.stderr)
    expect("the one-command declare needs no click", decision(s8.pre("Bash", {"command": "python3 tools/declare.py --cloud-defaults"})[1]) is None)
    r = sh("python3", str(TMP / "tools" / "declare.py"), "--places", "not offered in this session", "Skills and plugins", env=s8.env())
    expect("several places with one reason are recorded in one command", r.returncode == 0 and "Skills and plugins" in r.stdout, r.stdout + r.stderr)
    (TMP / "rv_bad.py").write_text('import sys, json\nsys.stdin.read()\nprint(json.dumps({"unsupported": ["I read the file: no read is in the log"]}))\n')
    (TMP / "rv_ok.py").write_text('import sys\nsys.stdin.read()\nprint(\'{"unsupported": []}\')\n')
    (TMP / "rv_crash.py").write_text("import sys\nsys.exit(3)\n")

    def stop_with(sess, msg, script):
        return hook("stop", dict(sess.base, hook_event_name="Stop", last_assistant_message=msg),
                    env_extra={"MM_REVIEWER_DISABLE": "", "MM_REVIEWER_CMD": f"python3 {TMP / script}"})
    s9 = Sess(); s9.satisfy()
    good9 = "Answer." + foot_all
    rc, out, _ = stop_with(s9, good9, "rv_bad.py")
    expect("the independent reviewer can refuse a reply whose claims the log does not support",
           (out or {}).get("decision") == "block" and "independent reviewer" in reason_of(out), reason_of(out))
    stop_with(s9, good9, "rv_bad.py")
    rc, out, _ = stop_with(s9, good9, "rv_bad.py")
    expect("the reviewer cannot loop: after two refusals it lets the reply through", (out or {}).get("decision") != "block", reason_of(out))
    s10 = Sess(); s10.satisfy()
    rc, out, _ = stop_with(s10, good9, "rv_ok.py")
    expect("a reviewer that finds nothing lets the reply through", (out or {}).get("decision") != "block", reason_of(out))
    rc, out, _ = stop_with(s10, good9, "rv_crash.py")
    expect("a reviewer that cannot run does not block the reply", (out or {}).get("decision") != "block", reason_of(out))

    # ---- 6c. the optional user-level copy (item 5): runs the checks from outside the repository, never twice inside it
    fake_home = Path(tempfile.mkdtemp(prefix="home_"))
    shutil.copytree(TMP, fake_home / ".mm-controls", ignore=shutil.ignore_patterns(".session", "__pycache__", "rv_*.py"))
    shutil.copy2(TMP / "tools" / "mm-controls-bootstrap.sh", fake_home / ".mm-controls-bootstrap.sh")
    elsewhere = Path(tempfile.mkdtemp(prefix="elsewhere_"))
    ul_cmd = json.loads((TMP / "controls" / "user-level-settings.json").read_text())["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"]
    ul_ev = json.dumps({"session_id": "u" + uuid.uuid4().hex[:6], "hook_event_name": "UserPromptSubmit", "prompt": "Where is the beige line?"})
    ul_env = dict(os.environ, HOME=str(fake_home), CLAUDE_PROJECT_DIR=str(elsewhere))
    r = sh("sh", "-c", ul_cmd, cwd=elsewhere, env=ul_env, input=ul_ev)
    expect("from a folder outside the repository the user-level copy runs the checks", r.returncode == 0 and ".mm-controls/tools/search.py" in r.stdout, r.stdout[:200] + r.stderr[:200])
    r = sh("sh", "-c", ul_cmd, cwd=TMP, env=dict(ul_env, CLAUDE_PROJECT_DIR=str(TMP)), input=ul_ev)
    expect("inside the repository the user-level copy does nothing, so the checks never run twice", r.returncode == 0 and not r.stdout.strip(), r.stdout[:200])
    r = sh("sh", "-c", ul_cmd, cwd=elsewhere, env=dict(ul_env, HOME=tempfile.mkdtemp(prefix="nohome_"), MM_CONTROLS_REPO="/nonexistent/repo"), input=ul_ev)
    expect("if the approved copy cannot be fetched, the action is blocked", r.returncode == 2, str(r.returncode) + r.stderr[:200])

    # ---- 6b. the search must be the owner's, and used (the owner's decision of 14 Oct 2026)
    footer = f"\nSearched: {places}\nCouldn't search: none"
    s = Sess("Is the beige line 30 above the section?")
    rc, out, _ = s.prompt("Is the beige line 30 above the section?")
    ctx = (out or {}).get("hookSpecificOutput", {}).get("additionalContext", "")
    expect("the message check tells Claude to search first, with the owner's words", "tools/search.py" in ctx and "beige" in ctx)
    expect("the message check names the settled decision the message touches", "Beige line between sections" in ctx)
    expect("the search tool runs without a click", s.pre("Bash", {"command": "python3 tools/search.py"})[1] is None)
    s.satisfy(search=False, drive_word="beige")
    rc, out, _ = s.stop("Answer." + footer)
    expect("a reply without the owner's message searched is refused", (out or {}).get("decision") == "block" and "owner's own words" in reason_of(out), reason_of(out))
    r = s.search()
    first = r.stdout.split("STRONGEST MATCHES")[1].strip().splitlines()[1] if "STRONGEST MATCHES" in r.stdout else ""
    expect("the search tool shows the strongest match first: the owner's own record", "START-HERE" in first and "beige" in first.lower(), first[:200])
    recs = [json.loads(l) for l in (TMP / ".session" / s.sid / "searches.jsonl").read_text().splitlines()]
    expect("the search tool records what it found in a log Claude cannot edit", recs and recs[-1]["places"]["Files"]["strong"] >= 1)
    rc, out, _ = s.stop("Answer." + footer)
    expect("a reply that ignores what the search found is refused", (out or {}).get("decision") == "block" and "quotes none" in reason_of(out), reason_of(out))
    quoted = "START-HERE says: \"Beige line between sections: 30 above, 30 below.\"" + footer
    rc, out, _ = s.stop(quoted)
    expect("a reply that quotes what was found is accepted", (out or {}).get("decision") != "block", reason_of(out))
    rc, out, _ = s.stop("Nothing found about this. Beige line between sections: 30 above, 30 below." + footer)
    expect("a reply saying nothing was found, when something was, is refused", (out or {}).get("decision") == "block" and "nothing was found" in reason_of(out), reason_of(out))
    s = Sess("Is the beige line 30 above the section?"); s.satisfy(drive_word="x")
    rc, out, _ = s.stop(quoted)
    expect("a Google Drive search without the owner's words does not count", (out or {}).get("decision") == "block" and "Google Drive" in reason_of(out), reason_of(out))
    s = Sess("Please rebuild the page."); s.satisfy()
    rc, out, _ = s.stop("Should the text column be 1220 wide?" + footer)
    expect("a question the owner has settled is refused and shown the answer", (out or {}).get("decision") == "block" and "settled" in reason_of(out) and "1220" in reason_of(out), reason_of(out))
    s = Sess("Let's change the text column width from 1220."); s.satisfy()
    rc, out, _ = s.stop("Do you want the text column wider than 1220?" + footer)
    expect("the owner can reopen a settled question", "but that is settled" not in reason_of(out), reason_of(out))
    s = Sess("Hi."); s.satisfy(skip=("Read",))
    rc, out, _ = s.stop("START-HERE says the column is 1220." + footer)
    expect("leaning on a record that was not read is refused", (out or {}).get("decision") == "block" and "leans on" in reason_of(out), reason_of(out))

    # ---- 7. the checks fail closed
    s = Sess()
    rc, out, err = hook("pre_tool", dict(s.base, hook_event_name="PreToolUse", tool_name="Edit", tool_input={"file_path": "x"}), env_extra={"HOOK_PYTHON": "/bin/false"})
    expect("if a check cannot run, the action is blocked", rc == 2)
    rc, out, err = hook("pre_tool", dict(s.base, hook_event_name="PreToolUse", tool_name="Edit", tool_input={"file_path": "x"}), env_extra={"HOOK_PYTHON": "/nonexistent/python"})
    expect("if Python is missing, the action is blocked", rc == 2)

    # ---- 8. integrity at session start
    s = Sess()
    rc, out, _ = hook("session_start", dict(s.base, hook_event_name="SessionStart", source="startup"))
    ctx = (out or {}).get("hookSpecificOutput", {}).get("additionalContext", "")
    expect("a clean copy starts normally and loads START-HERE", "INTEGRITY FAILURE" not in ctx and "Nothing goes live" in ctx)
    stp = TMP / ".claude" / "hooks" / "stop.py"
    orig = stp.read_text()
    stp.write_text(orig + "\n# tampered\n")
    s = Sess()
    rc, out, _ = hook("session_start", dict(s.base, hook_event_name="SessionStart", source="startup"))
    ctx = (out or {}).get("hookSpecificOutput", {}).get("additionalContext", "")
    expect("a changed check file is detected at session start", "INTEGRITY FAILURE" in ctx)
    s.satisfy()
    expect("and ordinary changes are then refused", decision(s.pre("Edit", {"file_path": work + "/pages/x.html", "new_string": "x"})[1]) == "deny")
    expect("but the owner can still approve repairing the checks", decision(s.pre("Edit", {"file_path": work + "/.claude/hooks/stop.py", "new_string": "x"})[1]) == "ask")
    stp.write_text(orig)
    (TMP / ".claude" / "settings.local.json").write_text('{"disableAllHooks": true}')
    s = Sess()
    rc, out, _ = hook("session_start", dict(s.base, hook_event_name="SessionStart", source="startup"))
    ctx = (out or {}).get("hookSpecificOutput", {}).get("additionalContext", "")
    expect("an attempt to switch the checks off locally is detected", "INTEGRITY FAILURE" in ctx)
    (TMP / ".claude" / "settings.local.json").unlink()

    # ---- 9. the size alarm and file-type guard (works on the whole history)
    r = sh("python3", str(TMP / "tools" / "size_alarm.py"), cwd=TMP)
    expect("size alarm passes on a clean repository", r.returncode == 0)
    (TMP / "hidden.pdf").write_bytes(b"%PDF-1.4 test")
    sh("git", "add", "hidden.pdf", cwd=TMP)
    sh("git", "commit", "-q", "-m", "oops", cwd=TMP)
    sh("git", "rm", "-q", "hidden.pdf", cwd=TMP)
    sh("git", "commit", "-q", "-m", "removed again", cwd=TMP)
    r = sh("python3", str(TMP / "tools" / "size_alarm.py"), cwd=TMP)
    expect("size alarm still catches a PDF that was committed and later deleted", r.returncode != 0 and "hidden.pdf" in r.stdout)

    # ---- 10. wording and spacing tools
    sys.path.insert(0, str(REPO / "tools"))
    import check_wording
    src = "The child is the builder of the man. Follow the child."
    d, _, _ = check_wording.compare("<html><body><nav>Menu</nav><p>The child is the builder of the man.</p><p>Follow the child.</p></body></html>", src)
    expect("wording check passes identical text and ignores the menu", not d)
    d, _, _ = check_wording.compare("<html><body><p>The child is the creator of the man.</p><p>Follow the child.</p></body></html>", src)
    expect("wording check catches one changed word", len(d) == 1)
    d, _, _ = check_wording.compare("<html><body><p>The child is the builder of the man. Follow the child. Written by me.</p></body></html>", src)
    expect("wording check catches words that are not the owner's", len(d) == 1 and d[0]["kind"] == "added on page")
    try:
        import measure_spacing
        import json as _j
        figs = {"figures": [{"id": 1, "text": "test", "kind": "gap", "expected": 20, "tolerance": 0, "viewport": "desktop",
                             "status": "mapped", "above": ".a", "below": ".b", "selector": None},
                            {"id": 2, "text": "unmapped", "kind": "gap", "expected": 5, "tolerance": 0, "viewport": "desktop",
                             "status": "pending", "above": None, "below": None, "selector": None}]}
        fp = TMP / "fig.json"
        fp.write_text(_j.dumps(figs))

        def page(margin):
            p = TMP / f"p{margin}.html"
            p.write_text(f"<html><body style='margin:0;font:20px sans-serif'><div class=a style='margin-top:40px'>Hello world</div>"
                         f"<div class=b style='margin-top:{margin}px'>Second line here</div></body></html>")
            return p
        r1 = measure_spacing.run(str(page(10)), "desktop", str(fp))
        r2 = measure_spacing.run(str(page(20)), "desktop", str(fp))
        v1, v2 = r1["figures"][0]["values"][0], r2["figures"][0]["values"][0]
        expect("spacing tool reads 10 more pixels when 10 pixels are added", abs((v2 - v1) - 10) < 0.01, f"{v1} -> {v2}")
        expect("spacing tool never passes a figure it cannot check", r1["figures"][1]["state"] == "NOT CHECKED")
        r3 = measure_spacing.run(str(page(10)), "desktop", str(fp))
        expect("two measurements of the same page agree", r3["figures"][0]["values"] == r1["figures"][0]["values"])

        # ---- the owner's ruler: the line the letters sit on to the top of the capitals below
        def caps_page(name, upper, lower_margin=0):
            q = TMP / f"{name}.html"
            q.write_text("<html><body style='margin:0;font:20px/40px sans-serif'>"
                         f"<p class=a style='margin:30px 0 0'>{upper}</p>"
                         f"<p class=b style='margin:{lower_margin}px 0 0'>HHHH HHHH</p></body></html>")
            return q
        f1 = {"figures": [{"id": 1, "text": "gap", "kind": "gap", "expected": 20, "tolerance": 0, "viewport": "desktop",
                           "status": "mapped", "above": ".a", "below": ".b", "selector": None}], "required_fonts": []}
        fp1 = TMP / "fig1.json"
        fp1.write_text(_j.dumps(f1))
        pc = caps_page("caps", "HHHH HHHH")
        pt = caps_page("tails", "gypsy jumpy")
        base_caps = measure_spacing.run(str(pc), "desktop", str(fp1), "baseline_to_capheight")["figures"][0]["values"][0]
        ink_caps = measure_spacing.run(str(pc), "desktop", str(fp1), "ink_to_ink")["figures"][0]["values"][0]
        expect("on capitals only (no tails) the two rulers agree within one pixel", abs(base_caps - ink_caps) <= 1.0, f"{base_caps} vs {ink_caps}")
        base_tails = measure_spacing.run(str(pt), "desktop", str(fp1), "baseline_to_capheight")["figures"][0]["values"][0]
        ink_tails = measure_spacing.run(str(pt), "desktop", str(fp1), "ink_to_ink")["figures"][0]["values"][0]
        expect("the owner's ruler ignores tails of g, y and p", abs(base_tails - base_caps) < 0.01, f"{base_tails} vs {base_caps}")
        expect("the old ink-to-ink ruler would have counted the tails", ink_tails < base_tails - 2, f"{ink_tails} vs {base_tails}")
        pm = caps_page("more", "HHHH HHHH", 10)
        base_more = measure_spacing.run(str(pm), "desktop", str(fp1), "baseline_to_capheight")["figures"][0]["values"][0]
        expect("the owner's ruler reads 10 more pixels when 10 pixels are added", abs((base_more - base_caps) - 10) < 0.01, f"{base_caps} -> {base_more}")
        want = round(base_caps)
        f1["figures"][0]["expected"] = want
        fp1.write_text(_j.dumps(f1))
        expect("a reading within half a pixel of the figure passes", measure_spacing.run(str(pc), "desktop", str(fp1), "baseline_to_capheight")["figures"][0]["state"] == "PASS")
        f1["figures"][0]["expected"] = want + 3
        fp1.write_text(_j.dumps(f1))
        expect("a reading 3 pixels off the figure fails", measure_spacing.run(str(pc), "desktop", str(fp1), "baseline_to_capheight")["figures"][0]["state"] == "FAIL")
        f1["required_fonts"] = ["A Font That Is Not On This Page"]
        fp1.write_text(_j.dumps(f1))
        expect("if the page's fonts are not loaded, no measurement is taken", "error" in measure_spacing.run(str(pc), "desktop", str(fp1), "baseline_to_capheight"))
    except ImportError as e:
        expect("spacing tool tests (needs the browser tools)", False, str(e))

    shutil.rmtree(TMP, ignore_errors=True)


if __name__ == "__main__":
    run()
    bad = [r for r in RESULTS if not r[1]]
    for name, ok, detail in RESULTS:
        print(("BLOCKED/OK  " if ok else "FAILED      ") + name + (f"  [{detail}]" if detail and not ok else ""))
    print(f"\n{len(RESULTS) - len(bad)} of {len(RESULTS)} checks behaved as expected.")
    sys.exit(1 if bad else 0)
