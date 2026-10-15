# Session 15 Oct 2026: making the checks run every session

Asked: how to ensure the checks run every time; what else remains to tighten; then the owner answered the list of remaining items.

Decided (owner):
- Sessions start inside the repository; sessions outside it and the user-level copy are not wanted (settled.json, id sessions-in-repository). CLAUDE.md now tells Claude to say so first if neither start message is present.
- This session runs in the desktop app and still has no tools for Chats, Project, Memory, Account memory or Folders: they stay "not offered in this session".
- Photo placement is raised by the owner in chat; nothing to build.
- The reviewer should see more of each result.
- "No doc exists to open" counts as a valid reason for Claude docs only (settled.json, id claude-docs-no-doc). The Claude docs tools open one named doc and cannot search all docs.
- Git route 1: commit on the old branch and open a new pull request.

Found:
- Pull request 15 (session-id fallback and the CLAUDE.md notice) is merged; GitHub's main moved to 1515a99.
- The integrity warning in this container was a false alarm: the start check compared with a stale local copy of main.
- Failed tool calls reached the log without their error text.
- ~/.claude/stop-hook-git-check.sh belongs to the cloud environment, not to this repository.

Done: reviewer excerpt 700 to 2,500 characters (start and end), configurable, total log capped; failed calls keep their reason; the start check fetches main with an explicit target; the new Claude docs reason with its restriction to that place. Tests: 154 of 155 behave as expected (the spacing tool needs a browser module).

Still open: the owner merges the new pull request; the Sensorial Curriculum rebuild (START-HERE "Still to do").
