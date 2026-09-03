"""Phase 0 -- validate the PDF before spending anything on LLM calls.

Answers four questions:

1. Is there a real text layer on every page? A scan without one needs
   `ocrmypdf --redo-ocr` before anything else. Finding this out at query time
   is far worse than finding it out now.
2. What is the offset between the printed folio and the PDF page index? Readers
   think in printed page numbers; PDF viewers address by index. Every downstream
   citation inherits an error here, so it is resolved once, up front.
3. Does the book have bookmarks, a table of contents, an index, a glossary?
   The back-of-book index in particular is a hand-curated term->pages mapping
   that gives us a controlled vocabulary and an eval gold set for free.
4. Roughly how many tokens is the book, to firm up the ingest cost estimate.

Run:  python -m stillfleetdb.probe
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import statistics
from dataclasses import asdict, dataclass, field
from pathlib import Path

import pymupdf

from . import config, pagenum

# Landmark headings we care about locating.
_LANDMARKS = {
    "contents": re.compile(r"\b(table of )?contents\b", re.I),
    "index": re.compile(r"^\s*index\s*$", re.I | re.M),
    "glossary": re.compile(r"\bglossary\b", re.I),
    "appendix": re.compile(r"\bappendix\b", re.I),
}

# Below this many characters a page is either blank (art plate) or has no text
# layer. We distinguish the two by checking whether the page carries images.
_SPARSE_PAGE_CHARS = 40


@dataclass
class PageProbe:
    pdf_index: int  # 1-based, matches PDF viewers and `#page=N`
    chars: int
    images: int
    folio: int | None
    head: str


@dataclass
class ProbeReport:
    pdf_path: str
    page_count: int
    encrypted: bool
    metadata: dict
    total_chars: int
    estimated_tokens: int
    pages_with_no_text: list[int]
    sparse_pages_with_images: list[int]
    folio_offset: int | None
    folio_coverage: float
    folio_unresolved_pages: list[int]
    has_bookmarks: bool
    bookmark_count: int
    bookmark_sample: list[list] = field(default_factory=list)
    landmarks: dict = field(default_factory=dict)


def _page_edge_lines(text: str, n: int = 3) -> tuple[list[str], list[str]]:
    lines = [ln for ln in (l.strip() for l in text.splitlines()) if ln]
    return lines[:n], lines[-n:]


def probe(pdf_path: Path, *, verbose: bool = True) -> ProbeReport:
    doc = pymupdf.open(pdf_path)

    # Folio <-> pdf-index resolution is shared with extract.py -- see pagenum.py
    # for the two-pass voting algorithm.
    folios = pagenum.resolve(doc)

    pages: list[PageProbe] = []
    for page in doc:
        text = page.get_text()
        pdf_index = page.number + 1
        pages.append(
            PageProbe(
                pdf_index=pdf_index,
                chars=len(text.strip()),
                images=len(page.get_images(full=True)),
                folio=folios.printed_page.get(pdf_index),
                head=" / ".join(_page_edge_lines(text, 2)[0])[:80],
            )
        )

    no_text = [p.pdf_index for p in pages if p.chars == 0]
    sparse_with_images = [
        p.pdf_index for p in pages if 0 < p.chars < _SPARSE_PAGE_CHARS and p.images
    ]
    # Pages without a consistent folio are expected -- full-bleed art plates and
    # front matter carry no printed number at all -- so this is a coverage
    # figure, not an error rate.
    unresolved = [p.pdf_index for p in pages if p.folio is None]

    toc = doc.get_toc()

    landmarks: dict[str, list[int]] = {}
    for name, pattern in _LANDMARKS.items():
        hits = []
        for page in doc:
            # Only look at the top of the page: we want the section heading,
            # not every passing mention of the word "index".
            head = page.get_text()[:300]
            if pattern.search(head):
                hits.append(page.number + 1)
        landmarks[name] = hits

    total_chars = sum(p.chars for p in pages)
    report = ProbeReport(
        pdf_path=str(pdf_path),
        page_count=doc.page_count,
        encrypted=doc.is_encrypted,
        metadata={k: v for k, v in (doc.metadata or {}).items() if v},
        total_chars=total_chars,
        estimated_tokens=round(total_chars / 4),
        pages_with_no_text=no_text,
        sparse_pages_with_images=sparse_with_images,
        folio_offset=folios.offset,
        folio_coverage=folios.coverage,
        folio_unresolved_pages=unresolved,
        has_bookmarks=bool(toc),
        bookmark_count=len(toc),
        bookmark_sample=toc[:25],
        landmarks=landmarks,
    )

    if verbose:
        _print_report(report, pages)
    doc.close()
    return report


def _print_report(r: ProbeReport, pages: list[PageProbe]) -> None:
    def rule(title: str) -> None:
        print(f"\n{title}\n{'-' * len(title)}")

    print(f"PDF: {Path(r.pdf_path).name}")
    print(f"Pages: {r.page_count}   Encrypted: {r.encrypted}")
    for k, v in r.metadata.items():
        print(f"  {k}: {v}")

    rule("1. Text layer")
    chars = [p.chars for p in pages]
    print(f"Total characters: {r.total_chars:,}")
    print(f"Median chars/page: {statistics.median(chars):,.0f}")
    if r.pages_with_no_text:
        print(
            f"!! {len(r.pages_with_no_text)} page(s) with NO text: "
            f"{r.pages_with_no_text[:30]}"
        )
        print("   If these are not intentionally blank, run:")
        print("   ocrmypdf --redo-ocr <in.pdf> <out.pdf>")
    else:
        print("OK - every page has extractable text.")
    if r.sparse_pages_with_images:
        print(
            f"Note: {len(r.sparse_pages_with_images)} sparse page(s) carrying "
            f"images (likely art plates): {r.sparse_pages_with_images[:20]}"
        )

    rule("2. Printed folio vs PDF index")
    if r.folio_offset is None:
        print("!! No folios detected. Page numbering must be resolved by hand.")
    else:
        detected = sum(1 for p in pages if p.folio is not None)
        print(f"Agreed offset: printed = pdf_index + ({r.folio_offset})")
        print(f"Confirmed on {detected}/{r.page_count} pages "
              f"({r.folio_coverage:.1%})")
        if r.folio_coverage < 0.8:
            print("!! Low coverage - inspect before trusting page citations.")
        print(f"No folio found on {len(r.folio_unresolved_pages)} page(s): "
              f"{r.folio_unresolved_pages[:20]}")

    rule("3. Structure")
    print(
        f"Bookmarks: {r.bookmark_count}"
        + (
            "  (entry segmentation is free)"
            if r.has_bookmarks
            else "  (none - segmentation needs an LLM pass)"
        )
    )
    for lvl, title, pg in r.bookmark_sample[:10]:
        print(f"  {'  ' * (lvl - 1)}{title[:60]}  p.{pg}")
    for name, hits in r.landmarks.items():
        print(f"{name:10s}: {hits if hits else 'not found'}")

    rule("4. Size")
    print(f"Estimated tokens: ~{r.estimated_tokens:,} (chars/4)")


def main() -> None:
    # Bookmark titles can carry non-ASCII glyphs (this book uses ☉), and
    # not every terminal this runs in is UTF-8 (Windows consoles often default
    # to cp1252) -- degrade to replacement characters rather than crash.
    sys.stdout.reconfigure(errors="replace")

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pdf", type=Path, default=None)
    ap.add_argument(
        "--json",
        type=Path,
        default=None,
        help="also write the report as JSON (keep it under data/)",
    )
    args = ap.parse_args()

    pdf_path = args.pdf or config.find_pdf()
    report = probe(pdf_path)

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(asdict(report), indent=2), encoding="utf-8")
        print(f"\nWrote {args.json}")


if __name__ == "__main__":
    main()
