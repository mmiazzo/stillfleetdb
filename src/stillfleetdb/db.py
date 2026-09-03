"""SQLite connection and schema management.

data/stillfleet.db holds the full extracted book text -- it is book content,
not a build artifact, and is gitignored (see config.DB_PATH and the project's
no-book-content-in-repo rule). Only schema.sql, which defines its shape, is
committed.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from . import config

_SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    """Open (creating if needed) the database and ensure the schema is applied.

    Safe to call repeatedly -- every statement in schema.sql is idempotent
    (CREATE ... IF NOT EXISTS), so this both creates a fresh database and
    brings an existing one up to date with no other bookkeeping required.
    """
    path = db_path or config.DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(_SCHEMA_PATH.read_text(encoding="utf-8"))
    return conn
