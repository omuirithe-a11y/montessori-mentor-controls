#!/bin/sh
# Fail-closed wrapper: if a check crashes, or Python is missing, the action is BLOCKED (exit 2), never let through.
# usage: run.sh <script-name-without-.py>
here="$(cd "$(dirname "$0")" && pwd)"
py="${HOOK_PYTHON:-python3}"
input="$(cat)"
out="$(printf '%s' "$input" | "$py" "$here/$1.py" 2>/tmp/.hook_err.$$)"
rc=$?
if [ "$rc" -eq 0 ]; then
  [ -n "$out" ] && printf '%s\n' "$out"
  rm -f /tmp/.hook_err.$$
  exit 0
fi
if [ "$rc" -eq 2 ]; then
  [ -n "$out" ] && printf '%s\n' "$out"
  cat /tmp/.hook_err.$$ >&2
  rm -f /tmp/.hook_err.$$
  exit 2
fi
echo "BLOCKED: an automatic check ($1) could not run (exit $rc). Nothing is allowed until it works. Tell the owner in plain English." >&2
head -c 400 /tmp/.hook_err.$$ >&2
rm -f /tmp/.hook_err.$$
exit 2
