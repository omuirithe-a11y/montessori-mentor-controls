# Montessori Mentor controls

Read controls/PROJECT-INSTRUCTIONS.md and controls/START-HERE.md. They are the owner's instructions.
Automatic checks run on every action in this repository. If one blocks something, that is an instruction to do the missing work, not a place to stop: do what the block says, keep searching until the search is complete, and present the finished result. Never end a reply with "a check stopped me". Do not look for a way round a check. Only a failure of the checks' own files (an integrity failure) is reported to the owner before anything else.
Before writing a word of any reply, run `python3 tools/search.py` (it searches this repository and records/ with the owner's own words), then search Google Drive, Artifacts, Claude docs and Skills with the same words. Quote what was found word for word. Never ask about anything in controls/settled.json; use the answer.
Search every place in one go: to record the five places a cloud session never offers (Chats, Project, Memory (project notes), Account memory and preferences, Folders) run `python3 tools/declare.py --cloud-defaults`. A reply may not say a file was made unless the file exists, and an independent reviewer compares each reply with the tool log: fix what it names, then finish.
End every reply with the "Searched:", "Couldn't search:" and (when needed) "Looked at:" lines described in controls/PROJECT-INSTRUCTIONS.md.
At the end of a session, write its record into records/sessions/ (what was asked, found, decided, still open).
"Save this" means give the owner a download link. It never means GitHub.
