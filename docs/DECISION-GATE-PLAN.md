# Plan: make "ask, don't decide" a check that bites

Written 14 October 2026 for the owner. Nothing in this plan is built yet. It is a plan of changes to this repository and to its GitHub settings, in the order that binds most. It answers one question: what would have stopped Claude choosing between two numbers, building the preview, and telling you afterwards.

## The honest starting point

A check cannot read Claude's mind. It cannot see a decision being made. What a check can see is the trace a decision leaves: a number that appears on a page without you having given it; a heading that was never confirmed; a reply that says "I chose"; two different numbers for one thing in your material. Every item below turns one of those traces into something that is refused, and makes you the only person who can lift the refusal. Where a decision leaves no trace at all, this plan says so in the last section rather than pretending.

The checks live in this repository and only run when Claude Code is opened on it. The chat where the three decisions were made was not covered by them, and no GitHub setting can reach into a chat. That is the single biggest limit, and it is addressed in the rollout section: page work goes through this repository or it is not covered.

## What binds, strongest first

### 1. GitHub refuses to merge while a decision is open or the sources disagree

This is the only layer nothing inside a session can undo.

- The main branch is locked with a ruleset: every change needs a pull request, your review as code owner, and the required checks passing; force pushes blocked; nobody may bypass. The plan for this was written on 13 October. I cannot see from inside a session whether it is switched on, so the first rollout step is for you to confirm it.
- A new required check, decision-gate, runs on every pull request and every push. It fails if the decision register (item 2) holds any open question, or if the design figures in START-HERE and in the figures file disagree on any number, or if the proof test (item 8) finds a single forbidden action getting through.
- The register, the figures file and every hook stay in the protected control paths, so a change to any of them needs your click in a session and your review on GitHub.

### 2. A decision register that only you can write to

A new file, controls/decisions.json, holds every question Claude has asked and every answer you have given, with your words verbatim and the date.

- Claude raises a question with a small tool. The tool records it as open and prints the exact text Claude must put in the reply: the question, the numbered options, nothing else. Claude cannot record an answer. Only the check that runs on your typed message can close a question, and only from your own words, for example "Q4: 2" or "question 4: 30".
- The file is locked to Claude the same way the search log is today: not by the file tools, not by a shell command, not with a click. Only the checks write it. The session-start integrity check allows it to differ from the approved version by added entries only.
- Because it lives in the repository, it lasts across sessions. That is also how rule 5 ("don't re-ask anything settled") gets a mechanism: Claude looks up the register before asking.

### 3. Everything stops while a question is open

While any register entry is open, these are refused outright: writing or changing any page file; the preview receipt; sending a preview file; publishing an artifact; pushing to GitHub; anything that goes live. Reading, searching and asking carry on. The refusal names the open question and tells Claude to wait for your answer. There is no way for Claude to clear it. This is the enforcement of "put the options in front of me": once an option set exists, the build cannot continue until you have picked.

### 4. No number reaches a page unless it came from you

This is the check that would have caught the three pairs of numbers.

- Before Claude can write a page, it must file a build brief for that page: every spacing, size, width and colour the page will use, each with its source. A source is one of three things: a figure number from the figures file (the tool refuses it if the value does not match the file), a quotation of your own words (the tool refuses it unless the words are found verbatim in your logged messages or in the register), or an answered question number. "Assumed", "usual", "same as before" and a bare number are refused, and the tool prints the question Claude has to ask instead.
- The preview gate then reads the finished page two ways. It scans every length in the page's own stylesheet (margins, padding, gaps, line heights, font sizes, widths, heights, indents). It also measures every gap between consecutive blocks on the rendered page, letters to letters, with the existing ruler. Every value must be an approved figure or a number from the brief. Any other number means no receipt, and without a receipt the preview cannot be sent. The reply lists the offending numbers so you can decide them.
- The brief also carries the heading map for the page (which lines are headings, which are sub-headings) and the tool refuses it unless that map is an answered question. That is rule 12 with teeth.

### 5. Two numbers for one thing becomes a question automatically

A conflict scan runs when the brief is filed and again on GitHub. For each figure it takes the figure's words (paragraph, heading, sub-heading, list, quotation, photo, footer and so on) and looks for that word next to a number in START-HERE, the figures file, your messages this session, and the Word text of the page being built. If it finds more than one distinct number for the same thing, it opens a question in the register with both numbers and where each was found, and item 3 stops the build until you answer. This is a word match, so it will sometimes ask when there was no real conflict. That costs you one answer. Missing a conflict costs a rebuilt page, so the scan errs towards asking.

### 6. The reply cannot carry a decision

The reply check that already enforces the footer gets three more rules.

- A number given in pixels, or next to a spacing word, that is not an approved figure and not in your words is refused. Claude has to turn it into a question.
- A sentence that admits a choice ("I chose", "I decided", "I assumed", "I picked", "I went with", "I took this to mean", "my reading") is refused, with the instruction to raise the question instead. This catches the honest confession, not the hidden choice. Its worth is that "I decided, and here is the preview" is a reply that can no longer be sent.
- When a question was raised this turn, the reply must contain its options, numbered, exactly as recorded. A question without options, or a reply that raises a question and then carries on building, is refused.

### 7. Your words are kept in full

Today the checks keep the first 2,000 characters of each message you type. Items 2, 4 and 5 verify quotations against your words, so the full text of every message is kept, in the session folder Claude cannot write to.

### 8. Proof that each new check bites

The proof test gains one scenario per rule above and runs on every change and every Monday: Claude cannot write the register by any route; an open question blocks a page write, a preview, a push and a publish; text Claude writes cannot answer a question; your "Q3: 2" closes it; a brief with an unsourced number is refused; a page with an unapproved number gets no receipt; a disagreement between START-HERE and the figures file fails on GitHub; a reply with "I assumed" is refused; a reply with an unapproved pixel number is refused. If any one of these ever stops biting, the required check turns red and GitHub emails you.

## Rollout

Step 1. Confirm the lock on the main branch. Open this page:

https://github.com/omuirithe-a11y/montessori-mentor-controls/settings/branches

Then: if there is a ruleset or rule for main that requires a pull request, your review, and the prove-it-bites and size-alarm checks, with force pushes blocked and no bypass, tell me it is on. If not, the 13 October steps in docs/PREVIEW-FOR-YOU.md still apply.

Step 2. Tell me to build it. I build items 2 to 8 in one pull request on a branch, with the proof test green, and send you the link. Nothing is switched on until you merge.

Step 3. After merging, add decision-gate to the required checks on the same settings page.

Step 4. The working rule that makes the rest matter: page work happens in Claude Code opened on this repository, nowhere else. A chat can answer questions, but it cannot build a page or send a preview. No GitHub setting can enforce this; only you can.

## Decisions I need from you

A. An unapproved number on a page.
1. Block the preview until you decide the number. This is the binding choice, and the one this plan assumes.
2. Report it in the reply, as the wording check does since 14 October, and let the preview through.

B. The heading map.
1. Every page build starts with a headings question, even when the Word file's styles make it obvious.
2. The question is asked only when the Word file has no heading styles, or when the styles and the brief disagree.

C. How you answer a question.
1. By number only ("Q4: 2"). Simplest to check; anything else is treated as not an answer.
2. By number or in free text ("question 4: thirty"). Your words are stored either way; free text is harder for the check to recognise, so an unrecognised answer leaves the question open and Claude asks again.

D. Where the register is kept.
1. In the repository, so answers last across sessions and GitHub can refuse to merge while a question is open. This plan assumes it.
2. In the session folder only. Simpler, but every new session starts with no memory of what you settled.

## What this plan cannot do

- It covers Claude Code sessions on this repository and nothing else. The incident happened in a chat; chats stay uncovered.
- It catches decisions that leave a trace: a number, a heading, a sentence, a conflict in the sources. A choice that leaves none, for example which photo goes where when the sizes are all approved, is not caught. If you want photo placement covered, it can be added to the brief as another question you answer, at the cost of one more answer per page.
- The conflict scan is a word match. It will sometimes ask when nothing conflicts, and it can miss a conflict phrased without the figure's word.
- The checks are files in this repository. The integrity check and the GitHub lock protect them, and the proof test shows they bite, but a session started with the checks switched off at the Claude Code level is not something a repository can see. Please never use the bypass-permissions mode.
- No check can make Claude think of a question it did not think of. What this plan does is make the two ways of not asking, a guessed number and a reply that tells you afterwards, impossible to deliver.
