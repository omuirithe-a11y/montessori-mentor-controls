"""Size alarm and file-type guard for the whole repository, including its history.
Warns at the warning size, fails at the block size, and fails if a forbidden file type or an oversize file is anywhere
in the repository or its history. Runs in GitHub on every change, so it cannot be skipped from inside a Claude session.
Usage: python3 tools/size_alarm.py"""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
cfg = json.loads((ROOT / "controls" / "config.json").read_text(encoding="utf-8"))


def git(*a):
    return subprocess.run(["git", "-C", str(ROOT), *a], capture_output=True, text=True).stdout


problems, warnings = [], []

total = 0
for dp, _, fs in os.walk(ROOT / ".git"):
    for f in fs:
        try:
            total += os.path.getsize(os.path.join(dp, f))
        except OSError:
            pass
mb = total / 1_000_000
if total >= cfg["repo_block_bytes"]:
    problems.append(f"Repository is {mb:.0f} MB. The block limit is {cfg['repo_block_bytes'] // 1_000_000} MB.")
elif total >= cfg["repo_warn_bytes"]:
    warnings.append(f"Repository is {mb:.0f} MB. The warning size is {cfg['repo_warn_bytes'] // 1_000_000} MB.")

# every file that has ever been in the repository
objs = git("rev-list", "--objects", "--all").splitlines()
paths = {}
for line in objs:
    parts = line.split(" ", 1)
    if len(parts) == 2:
        paths[parts[0]] = parts[1]
batch = subprocess.run(["git", "-C", str(ROOT), "cat-file", "--batch-check=%(objectname) %(objecttype) %(objectsize)"],
                       input="\n".join(paths), capture_output=True, text=True).stdout.splitlines()
seen = set()
for line in batch:
    sha, typ, size = line.split()
    if typ != "blob" or sha not in paths:
        continue
    name, size = paths[sha], int(size)
    ext = os.path.splitext(name.lower())[1]
    if ext in cfg["forbidden_extensions"] and name not in seen:
        problems.append(f"{name}: this file type is not allowed in the repository (it is in the history).")
        seen.add(name)
    elif size > cfg["max_file_bytes"] and name not in seen:
        problems.append(f"{name}: {size // 1000} KB is over the {cfg['max_file_bytes'] // 1000} KB limit for one file.")
        seen.add(name)

for w in warnings:
    print("::warning::" + w)
    print("WARNING: " + w)
for p in problems:
    print("::error::" + p)
    print("PROBLEM: " + p)
if not problems:
    print(f"Size alarm: OK. Repository is {mb:.1f} MB; no forbidden file types or oversize files in the history.")
sys.exit(1 if problems else 0)
