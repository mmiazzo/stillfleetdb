"""Printed-folio <-> PDF-index resolution.

Shared by probe.py (which reports the offset) and extract.py (which uses it to
populate pages.printed_page), so the two-pass voting algorithm has exactly one
implementation rather than two copies that could drift.
"""

from __future__ import annotations

import collections
import re
from dataclasses import dataclass, field

import pymupdf

# A folio is usually a bare number on its own line in the header or footer, but
# it is often set alongside a running head ("42   CHAPTER THREE"). We look at
# the first and last few lines of each page and accept a number anchored to
# either end of a line, requiring the rest of the line to be short so that we
# do not mistake body text or a table cell for a page number.
_BARE_NUMBER = re.compile(r"^\s*(\d{1,4})\s*$")
_EDGE_NUMBER = re.compile(r"^\s*(\d{1,4})\b(.{0,40})$|^(.{0,40}?)\b(\d{1,4})\s*$")


def _page_edge_lines(text: str, n: int = 3) -> tuple[list[str], list[str]]:
    lines = [ln for ln in (l.strip() for l in text.splitlines()) if ln]
    return lines[:n], lines[-n:]


def _folio_candidates(text: str) -> set[int]:
    """Every number that could plausibly be this page's folio.

    We deliberately do not assume the folio lives in the header or the footer
    -- this book puts it in the header, but relying on that would break on the
    next book and silently mis-cite pages. Gather candidates from both edges
    and let the whole-book vote in resolve() decide which is real.
    """
    head, tail = _page_edge_lines(text)
    candidates: set[int] = set()
    for line in head + tail:
        m = _BARE_NUMBER.match(line)
        if m:
            candidates.add(int(m.group(1)))
            continue
        m = _EDGE_NUMBER.match(line)
        if m:
            value = m.group(1) or m.group(4)
            if value:
                candidates.add(int(value))
    return candidates


@dataclass
class FolioMap:
    offset: int | None  # printed = pdf_index + offset
    coverage: float  # fraction of pages where a folio confirming the offset was found
    printed_page: dict[int, int | None] = field(default_factory=dict)  # pdf_index -> printed page


def resolve(doc: pymupdf.Document) -> FolioMap:
    """Two-pass folio resolution.

    Pass 1 gathers folio candidates per page and lets the whole book vote on
    the offset -- a folio is by definition near its page index, so the correct
    offset is the one the largest number of pages agree on; stray numbers from
    stat blocks and tables scatter across many different offsets and lose.

    Pass 2 keeps, per page, only the candidate consistent with that vote.
    """
    candidates: list[set[int]] = [_folio_candidates(page.get_text()) for page in doc]

    votes = collections.Counter(
        folio - (i + 1) for i, cands in enumerate(candidates) for folio in cands
    )
    offset: int | None = votes.most_common(1)[0][0] if votes else None

    printed_page: dict[int, int | None] = {}
    for i in range(doc.page_count):
        pdf_index = i + 1
        printed = None
        if offset is not None and (pdf_index + offset) in candidates[i]:
            printed = pdf_index + offset
        printed_page[pdf_index] = printed

    coverage = sum(1 for v in printed_page.values() if v is not None) / max(
        len(printed_page), 1
    )
    return FolioMap(offset=offset, coverage=round(coverage, 3), printed_page=printed_page)
