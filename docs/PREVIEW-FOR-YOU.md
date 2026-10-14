# What the automatic checks do (in plain English)

Written 13 October 2026. Nothing here is switched on yet. The checks sit in the repository, switched off, until you say so.

## The five checks you asked for

**1. The "prove it still bites" test.** Every time anything in the repository changes, and once every Monday, GitHub tries every forbidden action on purpose (58 of them) on a throwaway copy: editing a Word file, publishing without your "go", saving a PDF, switching the checks off, and so on. If even one gets through, the run fails and GitHub emails you.

**2. The size alarm.** GitHub checks the repository on every change. A warning appears at 100 MB. At 500 MB it fails. It also fails if a Word file, PDF, photo, zip or any file over 1 MB is anywhere in the repository, including deleted files in its history. That is the check that would have stopped the 2 GB problem.

**3. "Say what you looked at."** A reply cannot be finished unless it ends with these lines, and the lines match a log that Claude cannot write to:
- Searched: the places that were really searched in that reply
- Couldn't search: any place that wasn't, with one of four allowed reasons
- Looked at: what was looked at, required whenever the reply says checked, verified, done, matches, measured, tested or fixed

**4. One measuring standard.** The spacing tool measures only letters to letters. It never reports box figures. It waits for the fonts to finish loading, measures twice, and rejects the result if the two readings differ. A figure it has no way to measure yet is reported as NOT CHECKED. It is never reported as passing.

**5. Word for word.** The page text is compared with your Word text. Any added, missing or changed word is listed.

## The protections that go with them

- Nothing is uploaded or published unless you typed "go" in your last message. Even then, you get a click to approve. The "go" cannot be typed by Claude.
- Your originals (Word files, PDFs, photos) cannot be edited, moved, deleted or overwritten. Google Drive files cannot be changed, trashed or shared.
- "Save this" can never save to GitHub. Pushing to GitHub is refused unless your last message named it (push, commit or GitHub).
- Every file change needs your click.
- Before any change, Claude must have searched the 12 places in your instructions in that same reply, and read START-HERE from Google Drive. A copy of START-HERE lives in this repository and is checked against the Drive version.
- At the start of every session the checks check themselves. If any check file has been changed, or something tries to switch them off, everything is blocked and you are told.
- If a check crashes or can't run, the action is blocked, never let through.
- A page can't be sent as a preview unless it passed the spacing check. The wording check runs too, but since 14 October 2026 (your decision) it reports instead of blocking: every word that differs from the Word file is listed in the reply.

## Three decisions I need from you

**A. What does "letters to letters" mean exactly?**
1. From the lowest part of the letters above (including the tails of g, y and p) to the highest part of the letters below. This is the literal reading and is what the tool does now.
2. From the line the letters sit on, to the top of the capital letters below. Tails are ignored.

**B. How often must Claude search all 12 places?**
1. In every reply. This is what your instructions say, and it is the default now. It makes replies slower.
2. Once at the start of each chat.

**C. Should a preview be blocked while some figures can't be checked yet?**
1. No. The preview is allowed, and the reply must say which figures were NOT CHECKED. This is the default now.
2. Yes. No preview until every figure can be measured.

## What I still need from you for the spacing check

Your 17 design figures are in the repository, but each needs to be connected to the matching parts of your real pages (which blocks are "a blue heading", "a bold sub-heading" and so on). I can't guess that. I need one finished page file from the template, for example the live Culture Resources page saved as a file.

## What these checks cannot do

- They cannot make Claude put options in front of you, ask one short question, or use plain English. You still need to read what Claude writes.
- They only apply when Claude Code is opened on this repository. Work in any other chat or repository is not covered.
- A check that is written in the repository could in theory be edited by Claude. That is why GitHub keeps its own copy of the rules (see the next section), and why the repository checks its own files at the start of every session.
- I tested every check by feeding it the same messages Claude Code sends. I have not yet watched them run inside a live Claude Code session. The first real session is the final test.
- Your Claude plan (Max) does not have the one setting that locks checks across all your work. Only Teams and Enterprise plans have it.
- I could not confirm whether Claude Code's "bypass permissions" mode skips the checks. Please never use that mode.

## Switching it on (only when you decide)

Step 1: approve the changes. Open the pull request I created for this repository and click Merge. Its link is in my message.

Step 2: lock the main version. This is the part nothing inside a Claude session can undo. Open this page:

https://github.com/omuirithe-a11y/montessori-mentor-controls/settings/branches

Then:
1. Click "Add branch ruleset" (or "Add classic branch protection rule").
2. Name it main-locked and set the target branch to main.
3. Tick "Require a pull request before merging" and "Require review from Code Owners".
4. Tick "Require status checks to pass" and add **prove-it-bites** and **size-alarm**.
5. Tick "Block force pushes" and make sure nobody is allowed to bypass.
6. Save.

Step 3: switch the checks on. I copy controls/settings.armed.json to .claude/settings.json in a second pull request, which you merge.
