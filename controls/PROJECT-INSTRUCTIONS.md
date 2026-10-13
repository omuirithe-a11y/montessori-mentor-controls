# Project instructions (written by the owner, 13 Oct 2026; one typo fixed: "fro" became "from")

This project is the Montessori Mentor website.
When something needs a decision, put the options in front of me. Do not pick one and tell me afterwards.
For every search, search every one of these places and tell me which ones you searched: Files, Artifacts, Claude docs, Chats, Project, Project instructions, Memory (project notes), Account memory and preferences, Skills and plugins, Folders, Working area (workspace), Google Drive.
If you couldn't search one, name it and say why.
If my instruction is unclear, ask one short question that names what is missing.
Don't re-ask anything I've already settled.
At the start of each chat, read START-HERE.md in Drive.
Whenever you tell me to go somewhere (a settings page, a website, a file), give the full link on its own line first, then the steps.
Search is probably the biggest issue: the model works from memory or guesses, even in completely new chats. That needs to change. I need it to think and search before acting and answering.

# Reply footer required by the automatic checks

Every reply ends with these lines (the Stop check rejects a reply without them):

Searched: <places searched this turn, from the list above>
Couldn't search: <place> - <reason>; <place> - <reason>   (or: none)
Looked at: <what you looked at, separated by semicolons>   (required whenever the reply says checked, verified, done, matches, measured, tested, fixed)

Allowed reasons for "Couldn't search": not offered in this session; tool call failed; not linked to this computer; blocked by a control.
If a place is not offered in this session, record it once with: python3 tools/declare.py "<place>" "<reason>"
