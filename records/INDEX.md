# Records

The notes every Claude Code session on this repository can search. Started 14 Oct 2026 at the owner's decision ("I want all of them"); nothing older is carried forward (START-HERE: "Old records: deleted ... None is carried forward").

- controls/START-HERE.md - the owner's current instructions and design figures (the master copy).
- controls/PROJECT-INSTRUCTIONS.md - the owner's project instructions.
- controls/settled.json - the owner's settled decisions, each with the words that name it. A reply that asks about one is refused.
- sessions/ - one record per session: what was asked, what was found, what was decided, what is still open. Written at the end of every session.

How these are searched: `python3 tools/search.py` reads every text file in this repository, this folder included, with the words of the owner's message, and records what it found in the session's search log. The end-of-reply check then requires the reply to quote what was found.
