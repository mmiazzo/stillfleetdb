"""Tests for the Phase 1 extraction pipeline, against a synthetic PDF only."""

from __future__ import annotations

import sqlite3

from stillfleetdb import db, extract
from stillfleetdb.search import search_pages


def test_rows_from_chunk_page_row():
    chunk = {
        "text": "1\nGrit is a resource.",
        "page_boxes": [{"index": 0, "class": "page-header", "bbox": (0, 0, 1, 1), "pos": (0, 0)}],
    }
    page_row, table_rows = extract._rows_from_chunk(pdf_index=2, printed_page=1, chunk=chunk)

    assert page_row == (2, 1, chunk["text"], len(chunk["text"].strip()), 1, page_row[5])
    assert table_rows == []


def test_rows_from_chunk_extracts_tables_by_position():
    # pos slices into `text` -- verified against the real book's layout output
    # (a genuine table box on p.136 sliced cleanly via its pos offsets).
    text = "Weapons\n|Name|Damage|\n|---|---|\n|Pistol|1d6|\nEnd of page."
    table_start = text.index("|Name|")
    table_end = text.index("End of page.")
    chunk = {
        "text": text,
        "page_boxes": [
            {"index": 0, "class": "section-header", "pos": (0, 7)},
            {"index": 1, "class": "table", "pos": (table_start, table_end)},
        ],
    }
    page_row, table_rows = extract._rows_from_chunk(pdf_index=5, printed_page=3, chunk=chunk)

    assert table_rows == [(5, 1, text[table_start:table_end])]


def test_rows_from_chunk_blank_page_has_no_text():
    chunk = {"text": "", "page_boxes": []}
    page_row, table_rows = extract._rows_from_chunk(pdf_index=1, printed_page=None, chunk=chunk)

    assert page_row[3] == 0  # char_count
    assert page_row[4] == 0  # has_text
    assert table_rows == []


def test_extract_populates_pages_and_resolves_folios(synthetic_pdf, tmp_path):
    db_path = tmp_path / "test.db"
    extract.extract(pdf_path=synthetic_pdf, db_path=db_path, verbose=False)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = {r["pdf_index"]: r for r in conn.execute("SELECT * FROM pages")}

    assert len(rows) == 4

    # Page 1 is blank -- like the real book's full-bleed art plates: no text,
    # no folio.
    assert rows[1]["has_text"] == 0
    assert rows[1]["printed_page"] is None

    # Pages 2-4 carry folios 1, 2, 3 -> the resolved offset is -1 throughout.
    assert rows[2]["printed_page"] == 1
    assert rows[3]["printed_page"] == 2
    assert rows[4]["printed_page"] == 3

    meta = dict(conn.execute("SELECT key, value FROM meta"))
    assert meta["folio_offset"] == "-1"
    assert meta["page_count"] == "4"


def test_pages_fts_finds_known_text(synthetic_pdf, tmp_path):
    db_path = tmp_path / "test.db"
    extract.extract(pdf_path=synthetic_pdf, db_path=db_path, verbose=False)

    conn = db.connect(db_path)
    hits = search_pages(conn, "Grit")

    assert any(h.pdf_index == 2 for h in hits)


def test_extract_is_idempotent(synthetic_pdf, tmp_path):
    db_path = tmp_path / "test.db"
    extract.extract(pdf_path=synthetic_pdf, db_path=db_path, verbose=False)
    extract.extract(pdf_path=synthetic_pdf, db_path=db_path, verbose=False)

    conn = sqlite3.connect(db_path)
    assert conn.execute("SELECT COUNT(*) FROM pages").fetchone()[0] == 4
    assert conn.execute("SELECT COUNT(*) FROM pages_fts").fetchone()[0] == 4
