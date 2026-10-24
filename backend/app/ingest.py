"""Offline ingestion: markdown notes with frontmatter -> paragraph chunks -> embeddings -> Postgres.

Each chunk is one paragraph within a section (headings are kept as chunk metadata, and are part
of the text that gets embedded). Very short paragraphs, like a one-line footnote, are merged into
the previous paragraph of the same section so they don't become near-empty chunks.

Run with:  python -m app.ingest [--notes-dir DIR]
Idempotent: unchanged notes (by content hash) are skipped; changed notes are re-chunked.
Bump CHUNKER_VERSION when chunking changes, so every note is re-chunked on the next run.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import logging
import re
from dataclasses import dataclass
from pathlib import Path

import frontmatter

from app.config import settings
from app.db import get_pool, init_schema
from app.embeddings import embed_passages

log = logging.getLogger("ingest")

CHUNKER_VERSION = "paragraphs-v1"
MAX_CHUNK_CHARS = 1200
MIN_PARAGRAPH_CHARS = 120  # shorter paragraphs merge into the previous one in the same section
_HEADING = re.compile(r"^(#{1,3})\s+(.*)$")


@dataclass
class Note:
    note_id: str
    title: str
    ticker: str | None
    company: str | None
    sector: str | None
    rating: str | None
    previous_rating: str | None
    price_target: float | None
    currency: str | None
    analyst: str | None
    published_date: dt.date
    source_path: str
    body: str

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(
            f"{CHUNKER_VERSION}\n{self.title}\n{self.body}".encode()
        ).hexdigest()


@dataclass
class Chunk:
    chunk_id: str
    note_id: str
    chunk_index: int
    heading: str | None
    content: str


def parse_note(path: Path) -> Note:
    post = frontmatter.load(path)
    meta = post.metadata
    published = meta["date"]
    if isinstance(published, str):
        published = dt.date.fromisoformat(published)
    pt = meta.get("price_target")
    return Note(
        note_id=str(meta.get("note_id") or path.stem),
        title=str(meta["title"]),
        ticker=(str(meta["ticker"]).upper() if meta.get("ticker") else None),
        company=meta.get("company"),
        sector=meta.get("sector"),
        rating=meta.get("rating"),
        previous_rating=meta.get("previous_rating"),
        price_target=float(pt) if pt is not None else None,
        currency=meta.get("currency"),
        analyst=meta.get("analyst"),
        published_date=published,
        source_path=str(path),
        body=post.content.strip(),
    )


def _paragraphs(text: str) -> list[str]:
    """Split a section into paragraphs, merging very short ones into the previous paragraph."""
    paras: list[str] = []
    for para in (p.strip() for p in re.split(r"\n\s*\n", text)):
        if not para:
            continue
        if paras and len(para) < MIN_PARAGRAPH_CHARS:
            paras[-1] = f"{paras[-1]}\n\n{para}"
        else:
            paras.append(para)
    return paras


def _split_long(text: str, limit: int = MAX_CHUNK_CHARS) -> list[str]:
    """A guard for unusually long paragraphs: split on sentence boundaries."""
    if len(text) <= limit:
        return [text]
    parts, current = [], ""
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        if current and len(current) + len(sentence) + 1 > limit:
            parts.append(current.strip())
            current = ""
        current += sentence + " "
    if current.strip():
        parts.append(current.strip())
    return parts


def chunk_note(note: Note) -> list[Chunk]:
    """One chunk per paragraph, within markdown heading sections."""
    sections: list[tuple[str | None, list[str]]] = [(None, [])]
    for line in note.body.splitlines():
        m = _HEADING.match(line)
        if m:
            sections.append((m.group(2).strip(), []))
        else:
            sections[-1][1].append(line)

    chunks: list[Chunk] = []
    for heading, lines in sections:
        for para in _paragraphs("\n".join(lines)):
            for piece in _split_long(para):
                idx = len(chunks)
                chunks.append(Chunk(chunk_id=f"{note.note_id}#{idx}", note_id=note.note_id,
                                    chunk_index=idx, heading=heading, content=piece))
    return chunks


def embedding_text(note: Note, chunk: Chunk) -> str:
    """Contextual header so a chunk like 'Risks' still knows which company and date it's about."""
    who = " ".join(x for x in [note.company, f"({note.ticker})" if note.ticker else None] if x)
    header = " | ".join(
        x for x in [note.title, who, note.sector, note.published_date.isoformat(), chunk.heading] if x
    )
    return f"{header}\n{chunk.content}"


def ingest(notes_dir: Path) -> dict[str, int]:
    init_schema()
    paths = sorted(notes_dir.glob("**/*.md"))
    stats = {"seen": len(paths), "ingested": 0, "skipped": 0, "chunks": 0}
    pool = get_pool()
    with pool.connection() as conn:
        existing = dict(conn.execute("SELECT note_id, content_hash FROM notes").fetchall())

    for path in paths:
        note = parse_note(path)
        if existing.get(note.note_id) == note.content_hash:
            stats["skipped"] += 1
            continue
        chunks = chunk_note(note)
        vectors = embed_passages([embedding_text(note, c) for c in chunks])
        with pool.connection() as conn, conn.transaction():
            conn.execute("DELETE FROM notes WHERE note_id = %s", (note.note_id,))
            conn.execute(
                """
                INSERT INTO notes (note_id, title, ticker, company, sector, rating, previous_rating,
                                   price_target, currency, analyst, published_date, source_path,
                                   body, content_hash)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    note.note_id, note.title, note.ticker, note.company, note.sector, note.rating,
                    note.previous_rating, note.price_target, note.currency, note.analyst,
                    note.published_date, note.source_path, note.body, note.content_hash,
                ),
            )
            with conn.cursor() as cur:
                cur.executemany(
                    """
                    INSERT INTO chunks (chunk_id, note_id, chunk_index, heading, content, embedding)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    [
                        (c.chunk_id, c.note_id, c.chunk_index, c.heading, c.content, v)
                        for c, v in zip(chunks, vectors)
                    ],
                )
        stats["ingested"] += 1
        stats["chunks"] += len(chunks)
        log.info("ingested %s (%d chunks)", note.note_id, len(chunks))
    return stats


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--notes-dir", default=settings.notes_dir)
    args = parser.parse_args()
    stats = ingest(Path(args.notes_dir))
    log.info("done: %s", stats)


if __name__ == "__main__":
    main()
