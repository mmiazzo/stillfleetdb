"""Unit tests for the folio<->pdf-index resolution algorithm."""

from __future__ import annotations

import pymupdf

from stillfleetdb import pagenum


def test_folio_candidates_bare_number():
    assert pagenum._folio_candidates("1\nSome body text\nmore text") == {1}


def test_folio_candidates_ignores_long_lines():
    # A line that happens to start with digits but reads as body text (far
    # more than a folio-line's worth of trailing content) must not be treated
    # as a page number -- otherwise a stat block value could hijack the vote.
    text = "10 hit points remain after the attack lands squarely on the target"
    assert pagenum._folio_candidates(text) == set()


def test_resolve_offset_majority_vote():
    """Three pages agree on offset 0 (folio == pdf_index); a fourth page's
    stray leading number must not drag the result away from the majority.
    """
    doc = pymupdf.open()
    rect = pymupdf.Rect(72, 72, 500, 700)
    texts = [
        "1\nBody one",
        "2\nBody two",
        "3\nBody three",
        "50\nBody four with an unrelated stray number",
    ]
    for t in texts:
        page = doc.new_page()
        page.insert_textbox(rect, t, fontsize=11)

    result = pagenum.resolve(doc)

    assert result.offset == 0
    assert result.printed_page[1] == 1
    assert result.printed_page[2] == 2
    assert result.printed_page[3] == 3
    # Page 4's "50" is inconsistent with the winning offset (0 would require
    # folio 4, not 50), so it is correctly left unresolved rather than trusted.
    assert result.printed_page[4] is None


def test_resolve_no_folios_found():
    doc = pymupdf.open()
    doc.new_page()
    doc.new_page()

    result = pagenum.resolve(doc)

    assert result.offset is None
    assert result.coverage == 0.0
    assert all(v is None for v in result.printed_page.values())
