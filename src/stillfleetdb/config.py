"""Paths and shared constants.

Everything book-derived lives under DATA_DIR, which is gitignored. Nothing in
this module may write outside it.
"""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# All book-derived artifacts live here and are never committed: the source PDF,
# the SQLite database (which holds the full page text), the reviewed vocabulary,
# and the eval gold set.
DATA_DIR = Path(os.environ.get("STILLFLEET_DATA_DIR", REPO_ROOT / "data"))

DB_PATH = DATA_DIR / "stillfleet.db"
VOCABULARY_PATH = DATA_DIR / "vocabulary.yaml"
EVAL_QUERIES_PATH = DATA_DIR / "eval_queries.yaml"


def find_pdf() -> Path:
    """Locate the source rulebook.

    Honours STILLFLEET_PDF if set, otherwise takes the single PDF in DATA_DIR.
    Raises rather than guessing when the choice is ambiguous.
    """
    override = os.environ.get("STILLFLEET_PDF")
    if override:
        path = Path(override).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"STILLFLEET_PDF is set but not a file: {path}")
        return path

    if not DATA_DIR.is_dir():
        raise FileNotFoundError(
            f"No data directory at {DATA_DIR}. Put the rulebook PDF there."
        )

    candidates = sorted(DATA_DIR.glob("*.pdf"))
    if not candidates:
        raise FileNotFoundError(f"No PDF found in {DATA_DIR}.")
    if len(candidates) > 1:
        names = ", ".join(p.name for p in candidates)
        raise ValueError(
            f"Multiple PDFs in {DATA_DIR} ({names}). Set STILLFLEET_PDF to pick one."
        )
    return candidates[0]
