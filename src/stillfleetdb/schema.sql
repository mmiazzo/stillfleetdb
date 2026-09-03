-- Phase 1 schema. Pages and their tables only -- entries/facets are Phase 3.
--
-- This is book-derived content once populated (data/stillfleet.db), so the
-- database file itself is gitignored; only this schema is committed.

CREATE TABLE IF NOT EXISTS pages (
    pdf_index    INTEGER PRIMARY KEY,  -- 1-based, matches PDF viewers and #page=N
    printed_page INTEGER,              -- folio as printed in the book; NULL where none exists (art plates, front matter)
    markdown     TEXT NOT NULL,        -- pymupdf4llm markdown for this page
    char_count   INTEGER NOT NULL,
    has_text     INTEGER NOT NULL,     -- 0/1; false only for full-bleed art pages
    layout_json  TEXT NOT NULL         -- raw page_boxes from pymupdf4llm, for later phases
);

-- Table regions lifted out of page markdown by pymupdf4llm's layout detector,
-- each anchored to its page. Gear and roll tables are high-value direct-lookup
-- targets in an RPG book and get mangled if left flattened into surrounding
-- prose, so they get their own row instead.
CREATE TABLE IF NOT EXISTS tables (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    pdf_index INTEGER NOT NULL REFERENCES pages(pdf_index),
    box_index INTEGER NOT NULL,  -- index within the page's page_boxes list
    markdown  TEXT NOT NULL,
    UNIQUE (pdf_index, box_index)
);

-- Keyword search over page markdown. Porter stemmer for basic English
-- morphology. External-content table: pages stays the single source of text,
-- these triggers keep the index in sync with it.
CREATE VIRTUAL TABLE IF NOT EXISTS pages_fts USING fts5(
    markdown,
    content='pages',
    content_rowid='pdf_index',
    tokenize='porter'
);

CREATE TRIGGER IF NOT EXISTS pages_ai AFTER INSERT ON pages BEGIN
    INSERT INTO pages_fts(rowid, markdown) VALUES (new.pdf_index, new.markdown);
END;

CREATE TRIGGER IF NOT EXISTS pages_ad AFTER DELETE ON pages BEGIN
    INSERT INTO pages_fts(pages_fts, rowid, markdown) VALUES ('delete', old.pdf_index, old.markdown);
END;

CREATE TRIGGER IF NOT EXISTS pages_au AFTER UPDATE ON pages BEGIN
    INSERT INTO pages_fts(pages_fts, rowid, markdown) VALUES ('delete', old.pdf_index, old.markdown);
    INSERT INTO pages_fts(rowid, markdown) VALUES (new.pdf_index, new.markdown);
END;

-- Small key/value store for run metadata (folio offset, source PDF path, ...).
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
