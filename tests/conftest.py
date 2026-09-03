"""Shared test fixtures.

Every fixture here builds an entirely invented PDF at test time. Per the
project's rule against committing or testing against real book content, no
excerpt of the actual Stillfleet rulebook may appear anywhere under tests/.
"""

from __future__ import annotations

import pymupdf
import pytest


@pytest.fixture
def synthetic_pdf(tmp_path):
    """A tiny four-page PDF with invented content, mimicking the real book's
    shape just enough to exercise folio detection: one page with no printed
    folio (like a front-matter/art page), then three pages with consistent
    folios 1, 2, 3 -- so the correct offset is unambiguous (-1).
    """
    doc = pymupdf.open()
    rect = pymupdf.Rect(72, 72, 500, 700)

    # Page 1: no folio, no text at all -- like the real book's full-bleed art
    # plates, which have images but zero extractable text.
    doc.new_page()

    bodies = [
        "1\nGrit is a resource that measures a character's resolve under pressure.",
        "2\nAdvantage lets you roll two dice and keep the higher result.",
        "3\nWeapons: Pistol, Rifle, Blade.",
    ]
    for text in bodies:
        page = doc.new_page()
        page.insert_textbox(rect, text, fontsize=11)

    path = tmp_path / "synthetic.pdf"
    doc.save(path)
    doc.close()
    return path
