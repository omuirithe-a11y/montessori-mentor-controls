"""Word-for-word check: is every word on the page from the owner's Word text, and none missing?
Usage: python3 tools/check_wording.py <page.html> <source.docx|.txt|.md> [--ignore controls/wording-ignore.txt]
Page furniture (menu, footer, scripts) is skipped; extra lines to ignore go in the ignore file, one phrase per line."""
import argparse
import difflib
import re
import sys
import zipfile
from html.parser import HTMLParser
from pathlib import Path

SKIP = {"script", "style", "nav", "header", "footer", "noscript", "svg", "head", "title"}


class Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.depth = 0
        self.out = []

    def handle_starttag(self, tag, attrs):
        if tag in SKIP:
            self.depth += 1
        if tag in ("p", "br", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6"):
            self.out.append(" ")

    def handle_endtag(self, tag):
        if tag in SKIP and self.depth:
            self.depth -= 1

    def handle_data(self, data):
        if not self.depth:
            self.out.append(data)


def norm_words(s: str, ignore=()):
    s = s.replace(" ", " ").replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    s = s.replace("–", "-").replace("—", "-").replace("­", "")
    for phrase in ignore:
        s = s.replace(phrase, " ")
    return re.findall(r"[^\s]+", s)


def docx_text(path: Path) -> str:
    xml = zipfile.ZipFile(path).read("word/document.xml").decode("utf-8")
    xml = re.sub(r"</w:p>", "\n", xml)
    xml = re.sub(r"<w:tab/>", " ", xml)
    text = re.sub(r"<[^>]+>", "", xml)
    import html
    return html.unescape(text)


def source_text(path: Path) -> str:
    return docx_text(path) if path.suffix.lower() == ".docx" else path.read_text(encoding="utf-8")


def compare(page_html: str, source: str, ignore=()):
    p = Text()
    p.feed(page_html)
    a = norm_words(source)
    b = norm_words("".join(p.out), ignore)
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    diffs = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        diffs.append({"kind": {"replace": "changed", "delete": "missing from page", "insert": "added on page"}[tag],
                      "word": " ".join(a[i1:i2])[:80], "page": " ".join(b[j1:j2])[:80],
                      "context": " ".join(a[max(i1 - 4, 0):i1])})
    return diffs, len(a), len(b)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("page")
    ap.add_argument("source")
    ap.add_argument("--ignore")
    a = ap.parse_args()
    ignore = []
    ig = Path(a.ignore) if a.ignore else Path(__file__).resolve().parent.parent / "controls" / "wording-ignore.txt"
    if ig.exists():
        ignore = [l.strip() for l in ig.read_text(encoding="utf-8").splitlines() if l.strip()]
    diffs, na, nb = compare(Path(a.page).read_text(encoding="utf-8"), source_text(Path(a.source)), ignore)
    print(f"Compared {a.page} with {a.source}: {na} words in the source, {nb} on the page.")
    if not diffs:
        print("WORDING MATCHES word for word.")
        sys.exit(0)
    print(f"WORDING DIFFERS in {len(diffs)} places:")
    for d in diffs[:25]:
        print(f'  {d["kind"]}: source "{d["word"]}" / page "{d["page"]}" (after: ...{d["context"]})')
    sys.exit(1)


if __name__ == "__main__":
    main()
