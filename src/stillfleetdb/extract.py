"""Phase 1 -- extract the PDF into SQLite. No LLM calls.

Populates `pages` (one row per PDF page, markdown via pymupdf4llm, printed
folio resolved by pagenum.py) and `tables` (table regions the layout detector
lifts out of page markdown, each anchored to its page). Builds pages_fts (via
triggers in schema.sql) for immediate keyword search -- see db.py.

This is a full rebuild on every run, not an incremental one: it is fast and
free (no LLM calls), so idempotency comes from simply deleting and
re-inserting rather than from finer-grained checkpointing. The paid LLM
enrichment pass in a later phase is where resumability actually matters.

Run:  python -m stillfleetdb.extract
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import pymupdf
import pymupdf4llm

from . import config, db, pagenum


def _rows_from_chunk(
    pdf_index: int, printed_page: int | None, chunk: dict
) -> tuple[tuple, list[tuple]]:
    """Turn one pymupdf4llm page chunk into a `pages` row and `tables` rows.

    Kept separate from extract() so it can be tested against hand-built chunk
    dicts without depending on the (ML-based) layout detector actually
    recognizing a table in a test fixture.
    """
    text = chunk["text"]
    boxes = chunk.get("page_boxes", [])

    page_row = (
        pdf_index,
        printed_page,
        text,
        len(text.strip()),
        1 if text.strip() else 0,
        json.dumps(boxes),
    )

    table_rows = []
    for box in boxes:
        if box.get("class") == "table":
            start, end = box["pos"]
            table_rows.append((pdf_index, box["index"], text[start:end]))

    return page_row, table_rows


def extract(
    pdf_path: Path | None = None,
    db_path: Path | None = None,
    *,
    verbose: bool = True,
) -> None:
    pdf_path = pdf_path or config.find_pdf()
    conn = db.connect(db_path)

    doc = pymupdf.open(pdf_path)
    folios = pagenum.resolve(doc)
    if verbose:
        print(
            f"Folio offset: printed = pdf_index + ({folios.offset}), "
            f"coverage {folios.coverage:.1%}"
        )

    t0 = time.time()
    chunks = pymupdf4llm.to_markdown(doc, page_chunks=True, show_progress=verbose)
    if verbose:
        print(f"pymupdf4llm.to_markdown: {len(chunks)} pages in {time.time() - t0:.1f}s")

    page_rows = []
    table_rows = []
    for i, chunk in enumerate(chunks):
        pdf_index = i + 1
        page_row, chunk_table_rows = _rows_from_chunk(
            pdf_index, folios.printed_page.get(pdf_index), chunk
        )
        page_rows.append(page_row)
        table_rows.extend(chunk_table_rows)

    with conn:
        # Full rebuild -- see the module docstring on why this is fine here.
        conn.execute("DELETE FROM tables")
        conn.execute("DELETE FROM pages")
        conn.executemany(
            "INSERT INTO pages "
            "(pdf_index, printed_page, markdown, char_count, has_text, layout_json) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            page_rows,
        )
        conn.executemany(
            "INSERT INTO tables (pdf_index, box_index, markdown) VALUES (?, ?, ?)",
            table_rows,
        )
        conn.executemany(
            "INSERT INTO meta (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            [
                ("folio_offset", str(folios.offset)),
                ("folio_coverage", str(folios.coverage)),
                ("pdf_path", str(pdf_path)),
                ("page_count", str(len(page_rows))),
            ],
        )

    if verbose:
        print(
            f"Wrote {len(page_rows)} pages, {len(table_rows)} tables "
            f"to {db_path or config.DB_PATH}"
        )
    doc.close()
    conn.close()


def main() -> None:
    sys.stdout.reconfigure(errors="replace")

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pdf", type=Path, default=None)
    ap.add_argument("--db", type=Path, default=None)
    args = ap.parse_args()
    extract(args.pdf, args.db)


if __name__ == "__main__":
    main()
