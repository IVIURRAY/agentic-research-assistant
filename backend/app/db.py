"""Postgres connection pool and schema. One store holds notes, chunks, vectors and full-text."""

from __future__ import annotations

from pgvector.psycopg import register_vector
from psycopg_pool import ConnectionPool

from app.config import settings

SCHEMA = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS notes (
    note_id         text PRIMARY KEY,
    title           text NOT NULL,
    ticker          text,
    company         text,
    sector          text,
    rating          text,
    previous_rating text,
    price_target    numeric,
    currency        text,
    analyst         text,
    published_date  date NOT NULL,
    source_path     text,
    body            text NOT NULL,
    content_hash    text NOT NULL
);
CREATE INDEX IF NOT EXISTS notes_ticker_idx ON notes (ticker);
CREATE INDEX IF NOT EXISTS notes_sector_idx ON notes (sector);
CREATE INDEX IF NOT EXISTS notes_date_idx ON notes (published_date);

CREATE TABLE IF NOT EXISTS chunks (
    chunk_id    text PRIMARY KEY,
    note_id     text NOT NULL REFERENCES notes(note_id) ON DELETE CASCADE,
    chunk_index int  NOT NULL,
    heading     text,
    content     text NOT NULL,
    embedding   vector({dim}) NOT NULL,
    tsv         tsvector GENERATED ALWAYS AS (
                    to_tsvector('english', coalesce(heading, '') || ' ' || content)
                ) STORED
);
CREATE INDEX IF NOT EXISTS chunks_note_idx ON chunks (note_id);
CREATE INDEX IF NOT EXISTS chunks_tsv_idx ON chunks USING gin (tsv);
CREATE INDEX IF NOT EXISTS chunks_embedding_idx ON chunks USING hnsw (embedding vector_cosine_ops);

CREATE TABLE IF NOT EXISTS feedback (
    id          bigserial PRIMARY KEY,
    run_id      text NOT NULL,
    session_id  text,
    score       int NOT NULL,
    comment     text,
    created_at  timestamptz NOT NULL DEFAULT now()
);
"""

_pool: ConnectionPool | None = None


def _configure(conn) -> None:
    register_vector(conn)


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            settings.database_url,
            min_size=1,
            max_size=10,
            configure=_configure,
            open=True,
        )
    return _pool


def init_schema() -> None:
    # The vector extension must exist before register_vector can find its type,
    # so bootstrap it on a plain connection first.
    import psycopg

    with psycopg.connect(settings.database_url, autocommit=True) as conn:
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        conn.execute(SCHEMA.format(dim=settings.embed_dim))


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None
