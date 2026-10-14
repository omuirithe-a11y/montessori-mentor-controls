# Project instructions (written by the owner, 13 Oct 2026; one typo fixed: "fro" became "from"; on 13 Oct 2026 the START-HERE line was changed at the owner's request: START-HERE now lives in this repository, not in Drive)

This project is the Montessori Mentor website.
When something needs a decision, put the options in front of me. Do not pick one and tell me afterwards.
For every search, search every one of these places and tell me which ones you searched: Files, Artifacts, Claude docs, Chats, Project, Project instructions, Memory (project notes), Account memory and preferences, Skills and plugins, Folders, Working area (workspace), Google Drive.
If you couldn't search one, name it and say why.
If my instruction is unclear, ask one short question that names what is missing.
Don't re-ask anything I've already settled.
At the start of each chat, read START-HERE.md. It is kept in the GitHub repository omuirithe-a11y/montessori-mentor-controls, file controls/START-HERE.md, not in Drive. Read it at https://raw.githubusercontent.com/omuirithe-a11y/montessori-mentor-controls/main/controls/START-HERE.md
Whenever you tell me to go somewhere (a settings page, a website, a file), give the full link on its own line first, then the steps.
Search is probably the biggest issue: the model works from memory or guesses, even in completely new chats. That needs to change. I need it to think and search before acting and answering.

# Reply footer required by the automatic checks

Every reply ends with these lines (the Stop check rejects a reply without them):

Searched: <places searched this turn, from the list above>
Couldn't search: <place> - <reason>; <place> - <reason>   (or: none)
Looked at: <what you looked at, separated by semicolons>   (required whenever the reply says checked, verified, done, matches, measured, tested, fixed)

Allowed reasons for "Couldn't search": not offered in this session; tool call failed; not linked to this computer; blocked by a control.
If a place is not offered in this session, record it once with: python3 tools/declare.py "<place>" "<reason>"

# The search itself (the owner's decision of 14 Oct 2026, enforced by the checks)

Before anything is written: python3 tools/search.py  (no arguments: it searches this repository and records/ with the words of the owner's message, and prints them). Then Google Drive, Artifacts, Claude docs and Skills are searched with the same words; the Drive query must carry one of them.
The reply quotes what was found, word for word, from every place that had strong matches. It never says nothing was found while the search log holds matches. It never asks about a decision in controls/settled.json; it uses the answer. A new decision of the owner's goes into controls/settled.json in the reply it is made.
