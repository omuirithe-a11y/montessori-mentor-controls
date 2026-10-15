#!/bin/sh
# One-time setup for a Claude Code environment: makes the automatic checks run in every session, not only sessions that start inside this repository.
# Paste into the cloud environment's "Setup script" box, as:
#   curl -fsSL https://raw.githubusercontent.com/omuirithe-a11y/montessori-mentor-controls/main/tools/setup-environment.sh | sh
# Safe to run more than once. It keeps any other user-level settings already there.
set -e
repo="${MM_CONTROLS_REPO_RAW:-https://raw.githubusercontent.com/omuirithe-a11y/montessori-mentor-controls/main}"
home="${HOME:-/root}"
mkdir -p "$home/.claude"
curl -fsSL "$repo/tools/mm-controls-bootstrap.sh" -o "$home/.mm-controls-bootstrap.sh"
curl -fsSL "$repo/controls/user-level-settings.json" -o "$home/.mm-user-level-settings.json"
python3 - "$home" <<'PY'
import json, os, sys
home = sys.argv[1]
target = os.path.join(home, ".claude", "settings.json")
new = json.load(open(os.path.join(home, ".mm-user-level-settings.json")))["hooks"]
try:
    cur = json.load(open(target))
except (OSError, ValueError):
    cur = {}
hooks = cur.setdefault("hooks", {})
for event, groups in new.items():
    kept = [g for g in hooks.get(event, []) if "mm-controls-bootstrap" not in json.dumps(g)]
    hooks[event] = kept + groups
json.dump(cur, open(target, "w"), indent=2)
print("mm controls: user-level hooks installed in", target)
PY
