"""Search this repository with the owner's own words, and record what was found.

  python3 tools/search.py                      searches the owner's last message (the words are theirs, not Claude's)
  python3 tools/search.py "<a question>" [<extra word> ...]   searches one question, for example one Claude is about to ask

Every text file of the repository is read: the controls, the project instructions, the records folder, the documentation
and the checks themselves. Google Drive, Artifacts, Claude docs and Skills are searched with the connectors, with the same
words - this tool prints them. The strongest matches come first: a rare word counts for more than a common one, and a line
that carries several of the owner's words outranks a line that carries one.

What was found is written to the session's search log (.session/<id>/searches.jsonl), which Claude cannot edit. The
end-of-reply check reads it: the reply must quote what was found, may not say "nothing found" while the log holds matches,
and may not ask a question the settled list already answers. Owner's decision of 14 Oct 2026.
"""
import math
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / ".claude" / "hooks"))
os.environ.setdefault("CLAUDE_PROJECT_DIR", str(Path(__file__).resolve().parent.parent))
from lib import *  # noqa: E402

SHOW = 40                 # strongest matches printed
PER_PLACE_KEEP = 200      # matched lines kept in the log, per place
TEXT_EXT = {".md", ".txt", ".json", ".py", ".sh", ".yml", ".yaml", ".html", ".htm", ".css", ".js", ".csv"}
SKIP_DIRS = {".git", ".session", "__pycache__", "node_modules", "tests"}   # the proof test quotes questions on purpose


def weight(rel: str) -> float:
    """The owner's own records outrank data and code: START-HERE, the records, the instructions first; code last."""
    if rel in ("controls/START-HERE.md", "controls/PROJECT-INSTRUCTIONS.md", "CLAUDE.md") or rel.startswith("records/"):
        return 1.2
    if rel.endswith((".py", ".sh", ".yml", ".yaml", ".js", ".css")):
        return 0.7
    return 1.0


def place_of(rel: str) -> str:
    if rel.startswith("records/"):
        return "Records"
    if rel in ("controls/PROJECT-INSTRUCTIONS.md", "CLAUDE.md"):
        return "Project instructions"
    return "Files"


def files():
    root = project_dir()
    for dp, dns, fns in os.walk(root):
        dns[:] = sorted(d for d in dns if d not in SKIP_DIRS)
        for fn in sorted(fns):
            p = Path(dp) / fn
            if p.suffix.lower() not in TEXT_EXT or p.name.endswith(".pyc"):
                continue
            if (Path(dp) / fn).relative_to(root).as_posix() == "controls/orders.json":
                continue   # a copy of every message the owner typed: it would only echo the owner's words back as "matches"
            try:
                if p.stat().st_size > 1_000_000:
                    continue
                text = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            yield p.relative_to(root).as_posix(), text


def main():
    cfg = load_config()
    sid = current_session_id()
    if not sid:
        print("No session id is available, so the search cannot be recorded. Tell the owner.")
        sys.exit(1)
    st = load_state(sid)
    turn = int(st.get("turn", 0))
    args = [a for a in sys.argv[1:] if a.strip()]
    if args:
        question, extra, source = args[0], args[1:], "question"
    else:
        question, extra, source = str(st.get("last_prompt", "")), [], "owner's message"
    words, content = words_from(question)
    for w in extra:
        if w.lower() not in words:
            words.append(w.lower())
            content.append(w.lower())
    families = {}
    for c in content:
        for f in forms(c):
            families.setdefault(f, c)
    for w in words:
        families.setdefault(w, w)

    matches, hits, per_file, n_lines, scanned = [], {w: 0 for w in words}, {}, 0, 0
    if content:
        for rel, text in files():
            scanned += 1
            lines = text.splitlines()
            n_lines += len(lines)
            for i, line in enumerate(lines):
                low = line.lower()
                m = [w for w in words if w in low]
                if not m:
                    continue
                for w in m:
                    hits[w] += 1
                ctx = " / ".join(x.strip()[:200] for x in lines[max(0, i - 1):i + 2] if x.strip())
                fams = sorted({families.get(w, w) for w in m})
                phrase = any(" " in w for w in m)
                matches.append({"file": rel, "line": i + 1, "words": sorted(set(m)), "families": fams,
                                "phrase": phrase, "text": line.strip()[:400], "context": ctx[:480]})
                per_file[rel] = per_file.get(rel, 0) + 1
    idf = {w: math.log((n_lines + 1) / (1 + n)) for w, n in hits.items()}

    def score(m):
        best = {}
        for w in m["words"]:
            k = families.get(w, w)
            best[k] = max(best.get(k, 0), idf[w] * (3 if " " in w else 1))
        return sum(best.values()) * weight(m["file"])

    single_max = int(cfg.get("strong_single_word_max_hits", 50))
    for m in matches:
        m["score"] = round(score(m), 2)
        # a STRONG match carries two of the owner's words, or a phrase of theirs, or their one word when it is rare
        m["strong"] = bool(len(m["families"]) >= 2 or m["phrase"]
                           or (len(content) == 1 and sum(hits[f] for f in words if families.get(f) == content[0]) <= single_max))
    ranked = sorted(matches, key=lambda m: (m["strong"], m["score"]), reverse=True)

    places = {}
    for m in ranked:
        pl = place_of(m["file"])
        places.setdefault(pl, {"matches": 0, "strong": 0, "files": {}, "lines": []})
        places[pl]["matches"] += 1
        places[pl]["strong"] += 1 if m["strong"] else 0
        places[pl]["files"][m["file"]] = places[pl]["files"].get(m["file"], 0) + 1
        if len(places[pl]["lines"]) < PER_PLACE_KEEP:
            places[pl]["lines"].append({"file": m["file"], "line": m["line"], "text": m["text"], "strong": m["strong"],
                                        "words": m["words"]})
    for pl in ("Files", "Project instructions") + (("Records",) if (project_dir() / "records").is_dir() else ()):
        places.setdefault(pl, {"matches": 0, "strong": 0, "files": {}, "lines": []})

    settled = [(e, present) for e, present in settled_matches(question, load_settled())]

    print(f"SEARCHED {scanned} files ({n_lines} lines) of this repository for the {source}: {question[:300]!r}")
    if not content:
        print("No content words in it: nothing to search for. A reply to it needs no search of the places.")
    else:
        shown = [w for w in words if " " in w] + content
        print(f"WORDS (from the {source} itself, with their other forms): " + ", ".join(shown))
        print(f"{len(matches)} matching lines, {sum(1 for m in matches if m['strong'])} strong; per word: "
              + ", ".join(f"{w} {n}" for w, n in hits.items() if n) + "; none for: " + (", ".join(w for w, n in hits.items() if not n) or "-"))
        print(f"\n#### THE {min(SHOW, len(ranked))} STRONGEST MATCHES (strong = two of the owner's words, a phrase, or a rare word)")
        for m in ranked[:SHOW]:
            print(f"  {'*' if m['strong'] else ' '} {m['file']}:{m['line']} [{', '.join(m['families'][:5])}]: {m['context'][:400]}")
        print("\n#### EVERY PLACE AND ITS MATCHES")
        for pl, d in places.items():
            print(f"  {pl}: {d['matches']} lines ({d['strong']} strong) in {len(d['files'])} files"
                  + (": " + ", ".join(f"{f} ({n})" for f, n in sorted(d["files"].items(), key=lambda x: -x[1])[:8]) if d["files"] else ""))
    if settled:
        print("\n#### SETTLED DECISIONS THIS TOUCHES - use them; do not ask about them again")
        for e, present in settled:
            print(f"  - {e.get('topic', '')} ({e.get('date', '')}): {e.get('answer', '')}  [matched: {', '.join(present)}]")
    print("\nNOW: search Google Drive, Artifacts, Claude docs and Skills with the same words (the Drive query must carry one of them)."
          " In the reply, quote what was found word for word, and say which places had nothing.")

    append_search(sid, {"turn": turn, "source": source, "question": question[:2000], "content": content, "words": words,
                        "files_scanned": scanned, "lines": n_lines, "matches": len(matches),
                        "strong": sum(1 for m in matches if m["strong"]),
                        "hits": {w: n for w, n in hits.items() if n},
                        "places": places,
                        "settled": [e.get("id") for e, _ in settled]})


if __name__ == "__main__":
    main()
