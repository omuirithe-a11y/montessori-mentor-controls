"""File the build brief for a page. Without a brief the preview gate refuses the page (owner's decision of 15 Oct 2026, A=1).
Usage: python3 tools/brief.py <page-name> [--word <file.docx>] (--heading "<line>" ... | --no-headings) [--headings-source q:<n>] <entry> ...
Each entry is  VALUE::LABEL::SOURCE  where VALUE is a number (with px, em, % or none), LABEL says what it is for, and SOURCE is one of:
    fig:<n>        figure n of controls/design-figures.json (the value must be one of that figure's numbers)
    quote:<words>  the owner's own words, found verbatim in their logged messages or in an answered question (the value must be in the words)
    q:<n>          an answered question Q<n> (the value must be in the chosen answer)
Anything else ("assumed", "usual", "same as before", a bare number) is refused and the question to ask is printed.
The heading map is asked as a question only when the Word file has no heading styles, or when the styles and the brief disagree (owner's decision B=2).
The brief is also scanned for two numbers for one thing: a conflict opens a question in the register, and the build stops until the owner answers it."""
import argparse
import json
import os
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / ".claude" / "hooks"))
sys.path.insert(0, str(ROOT / "tools"))
os.environ.setdefault("CLAUDE_PROJECT_DIR", str(ROOT))
from lib import *  # noqa: E402
import check_wording  # noqa: E402

ap = argparse.ArgumentParser(add_help=False)
ap.add_argument("page")
ap.add_argument("entries", nargs="*")
ap.add_argument("--word")
ap.add_argument("--heading", action="append", default=[])
ap.add_argument("--no-headings", action="store_true")
ap.add_argument("--headings-source")
try:
    args = ap.parse_args()
except SystemExit:
    print(__doc__)
    sys.exit(1)

sid = os.environ.get("CLAUDE_SESSION_ID")
if not sid:
    print("No session id is available, so the brief cannot be filed. Tell the owner.")
    sys.exit(1)
st = load_state(sid)
turn = int(st.get("turn", 0))
cfg = load_config()
stem = Path(args.page).stem
refusals = []


def ask_block(q):
    out = f"{q['id']}. {q['text']}\n" + "\n".join(f"{i}. {o}" for i, o in enumerate(q["options"], 1)) + f"\nAnswer with: {q['id']}: <number>"
    return out


def raise_once(text, options):
    norm = normalise_quote(text)
    for q in read_register()["questions"]:
        if normalise_quote(q["text"]) == norm:
            return q, False
    return raise_question(text, options, sid, turn), True


def docx_headings(path):
    xml = zipfile.ZipFile(path).read("word/document.xml").decode("utf-8")
    heads = []
    for para in re.findall(r"<w:p[ >].*?</w:p>", xml, re.S):
        m = re.search(r'<w:pStyle w:val="([^"]+)"', para)
        if m and re.match(r"(?i)^(heading|title|subtitle)", m.group(1).replace(" ", "")):
            t = re.sub(r"<[^>]+>", "", re.sub(r"<w:tab/>", " ", para)).strip()
            if t:
                heads.append(t)
    return heads


owner_words = " ".join(p.get("prompt", "") for p in read_prompts(sid)) + " " + " ".join(
    q.get("answered_words") or "" for q in read_register()["questions"] if q.get("status") == "answered")
figs = {f["id"]: f for f in json.loads((ROOT / "controls" / "design-figures.json").read_text(encoding="utf-8")).get("figures", [])}
answered = {q["id"]: q for q in read_register()["questions"] if q.get("status") == "answered"}

# ---------------------------------------------------------------- the numbers, each with a source the owner can check
numbers = []
for raw in args.entries:
    parts = raw.split("::")
    if len(parts) != 3:
        refusals.append(f'"{raw}": write it as VALUE::LABEL::SOURCE')
        continue
    value, label, source = (p.strip() for p in parts)
    vn = numbers_in(value)
    if len(vn) != 1:
        refusals.append(f'"{raw}": the value must be one number')
        continue
    v = next(iter(vn))
    ok = False
    kind, _, rest = source.partition(":")
    if kind == "fig":
        f = figs.get(int(rest)) if rest.isdigit() else None
        ok = bool(f) and (v in numbers_in(f.get("text", "")) or v == canon_number(f.get("expected", -1)))
        if not ok:
            refusals.append(f'"{raw}": figure {rest} does not contain {v}' if f else f'"{raw}": there is no figure {rest}')
    elif kind == "quote":
        words = rest.strip().strip('"')
        ok = len(normalise_quote(words).split()) >= 2 and normalise_quote(words) in normalise_quote(owner_words) and v in numbers_in(words)
        if not ok:
            refusals.append(f'"{raw}": those words are not in the owner\'s logged messages or answered questions, or do not contain {v}')
    elif kind == "q":
        q = answered.get("Q" + rest)
        ok = bool(q) and v in numbers_in(q.get("answer_text", ""))
        if not ok:
            refusals.append(f'"{raw}": Q{rest} is not an answered question whose answer contains {v}')
    else:
        refusals.append(f'"{raw}": the source "{source}" is not allowed (use fig:<n>, quote:<the owner\'s words> or q:<n>); a number nobody approved is a question for the owner')
    if ok:
        numbers.append({"value": v, "label": label, "source": source})

# ---------------------------------------------------------------- the heading map (B=2: a question only when needed)
word_text = ""
word_heads = None
if args.word:
    try:
        word_heads = docx_headings(Path(args.word)) if args.word.lower().endswith(".docx") else []
        word_text = check_wording.source_text(Path(args.word))
    except Exception as exc:
        refusals.append(f"the Word file could not be read: {exc}")
headings_source = None
if not args.heading and not args.no_headings:
    refusals.append("give the heading map: --heading \"<line>\" for each heading line, or --no-headings")
else:
    brief_set = {normalise_quote(h) for h in args.heading}
    if word_heads and brief_set == {normalise_quote(h) for h in word_heads}:
        headings_source = "word-styles"
    elif not args.heading and not word_heads:
        headings_source = "none-claimed"  # the brief claims no headings and the Word file shows none: nothing to ask
    elif args.headings_source and args.headings_source.startswith("q:") and ("Q" + args.headings_source[2:]) in answered:
        headings_source = args.headings_source
    else:
        why = "The Word file has no heading styles" if not word_heads else "The Word file's heading styles and the brief disagree"
        if args.word is None:
            why = "No Word file was given, so there is no heading style map to compare with"
        brief_map = "; ".join(args.heading) if args.heading else "(no headings)"
        opts = [f"The brief's map: {brief_map}"]
        opts.append(f"The Word styles' map: {'; '.join(word_heads)}" if word_heads else "I will send the heading map myself")
        q, new = raise_once(f"Which lines of {stem} are headings and which are sub-headings? {why}.", opts)
        refusals.append(f"the heading map needs the owner's answer. {'Raised' if new else 'Already open:'} {q['id']}. Put this in the reply and wait:\n{ask_block(q)}")

# ---------------------------------------------------------------- two numbers for one thing become a question automatically
conflicts = []
ctx = re.compile(cfg.get("conflict_context_regex", "$^"))
base_text = (ROOT / "controls" / "START-HERE.md").read_text(encoding="utf-8")
allowed = {canon_number(x) for x in cfg.get("gate_always_allowed", [])}
for e in load_settled():
    base_nums = numbers_in(e.get("answer", ""))
    if not base_nums:
        continue
    for w in e.get("words", []):
        for src_name, src in (("the owner's messages", owner_words), ("the Word text", word_text)):
            src = ANSWER_RE.sub(" ", src)  # "Q4: 2" is an answer, not a measurement
            for m in re.finditer(re.escape(w), src, re.I):
                win = src[max(0, m.start() - 40): m.end() + 40]
                for nm in re.finditer(r"(?<![\w#.])(\d+(?:\.\d+)?)", win):
                    n = canon_number(nm.group(1))
                    if not ctx.search(win[max(0, nm.start() - 14): nm.end() + 14]):
                        continue  # only a number right next to a spacing word counts
                    if n in base_nums or n in allowed or (1900 <= float(n) <= 2100) or len(n) > 4:
                        continue
                    conflicts.append((e, n, src_name, " ".join(win.split())))
seen, opened = set(), []
for e, n, src_name, snippet in conflicts:
    if (e["id"], n) in seen or len(opened) >= 5:
        continue
    seen.add((e["id"], n))
    q, new = raise_once(f"Two numbers for {e['topic'].lower()}: the approved figure says \"{e['answer']}\" ({e.get('source', 'START-HERE')}), "
                        f"but {src_name} has {n} near \"{snippet[:80]}\". Which applies?",
                        [f"The approved figure: {e['answer']}", f"{n}, as found in {src_name}"])
    opened.append((q, new))
if opened:
    refusals.append("two numbers for one thing were found, so the build stops until the owner answers. Put these in the reply:\n\n" + "\n\n".join(ask_block(q) for q, _ in opened))

if refusals:
    print("BRIEF NOT FILED:")
    for r in refusals:
        print("  - " + r)
    sys.exit(1)

d = ROOT / ".session" / "briefs"
d.mkdir(parents=True, exist_ok=True)
(d / f"{stem}.json").write_text(json.dumps({"page": stem, "filed": time.strftime("%Y-%m-%d"), "session": safe_id(sid), "word": args.word,
                                            "numbers": numbers, "headings": args.heading, "headings_source": headings_source}, indent=1, ensure_ascii=False), encoding="utf-8")
print(f"BRIEF FILED for {stem}: {len(numbers)} numbers with sources, {len(args.heading)} headings ({headings_source}).")
