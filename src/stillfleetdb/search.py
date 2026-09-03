"""Minimal keyword search over pages_fts -- the Phase 1 deliverable.

Plain FTS5 MATCH with a snippet, nothing more. This alone already answers a
large share of real queries and shows what's genuinely missing; Phase 4 will
merge this against entries_fts and terms in a ranked blend.

Run:  python -m stillfleetdb.search "grit"
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from dataclasses import dataclass

from . import db

_TOKEN = re.compile(r"\w+")


@dataclass
class SearchHit:
    pdf_index: int
    printed_page: int | None
    snippet: str


def _match_query(user_query: str) -> str:
    """Bag-of-words OR query, each token quoted so FTS5 syntax characters in
    the user's input (hyphens, quotes, ...) can't break the MATCH expression.
    """
    tokens = _TOKEN.findall(user_query)
    if not tokens:
        return '""'
    return " OR ".join(f'"{t}"' for t in tokens)


def search_pages(conn: sqlite3.Connection, query: str, limit: int = 10) -> list[SearchHit]:
    rows = conn.execute(
        """
        SELECT p.pdf_index, p.printed_page,
               snippet(pages_fts, 0, '[', ']', '...', 12) AS snip
        FROM pages_fts
        JOIN pages p ON p.pdf_index = pages_fts.rowid
        WHERE pages_fts MATCH ?
        ORDER BY bm25(pages_fts)
        LIMIT ?
        """,
        (_match_query(query), limit),
    ).fetchall()
    return [SearchHit(r["pdf_index"], r["printed_page"], r["snip"]) for r in rows]


def main() -> None:
    sys.stdout.reconfigure(errors="replace")

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("query")
    ap.add_argument("--limit", type=int, default=10)
    args = ap.parse_args()

    conn = db.connect()
    hits = search_pages(conn, args.query, args.limit)
    if not hits:
        print("No matches.")
        return
    for h in hits:
        label = f"p.{h.printed_page}" if h.printed_page is not None else f"pdf#{h.pdf_index}"
        print(f"{label:>6}  {h.snippet}")


if __name__ == "__main__":
    main()
