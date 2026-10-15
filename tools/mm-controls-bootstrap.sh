#!/bin/sh
# Runs one of the repository's checks from a session that did not start inside the repository.
# Install: copy this file to ~/.mm-controls-bootstrap.sh (see docs/USER-LEVEL-HOOKS.md). usage: mm-controls-bootstrap.sh <check-name>
# It keeps a shallow copy of the approved repository in ~/.mm-controls (refreshed at session start) and runs the check from it.
# If anything is missing or broken the action is BLOCKED (exit 2), as in the repository's own run.sh.
d="${MM_CONTROLS_DIR:-$HOME/.mm-controls}"
repo="${MM_CONTROLS_REPO:-https://github.com/omuirithe-a11y/montessori-mentor-controls}"
if [ "$1" = "session_start" ] || [ ! -d "$d/.claude/hooks" ]; then
  if [ -d "$d/.git" ]; then git -C "$d" fetch --depth=1 origin main >/dev/null 2>&1 && git -C "$d" reset --hard origin/main >/dev/null 2>&1
  else git clone --depth 1 "$repo" "$d" >/dev/null 2>&1; fi
fi
if [ ! -f "$d/.claude/hooks/run.sh" ]; then
  echo "BLOCKED: the automatic checks could not be fetched from $repo. Nothing is allowed until they can. Tell the owner in plain English." >&2
  exit 2
fi
MM_USER_LEVEL=1 CLAUDE_PROJECT_DIR="$d" exec sh "$d/.claude/hooks/run.sh" "$1"
