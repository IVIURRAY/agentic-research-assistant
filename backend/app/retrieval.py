"""Hybrid retrieval: pgvector (dense) + Postgres full-text (sparse), fused with RRF, then reranked.

Metadata filters (ticker, sector, date range) are applied in SQL to *both* legs, before ranking,
so a filter can never be "forgotten" by the ranker. This is also where per-user entitlement
filtering would go later: in the retrieval filter, not the prompt.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import asdict, dataclass, field
from typing import Any

from app.config import settings
from app.db import get_pool
from app.embeddings import embed_query
from app.rerank import get_reranker
from app.telemetry import span


@dataclass
class SearchFilters:
    ticker: str | None = None
    sector: str | None = None
    date_from: dt.date | None = None
    date_to: dt.date | None = None

    def sql(self) -> tuple[str, list[Any]]:
        clauses, params = [], []
        if self.ticker:
            clauses.append("n.ticker = %s")
            params.append(self.ticker.upper())
        if self.sector:
            clauses.append("n.sector ILIKE %s")
            params.append(self.sector)
        if self.date_from:
            clauses.append("n.published_date >= %s")
            params.append(self.date_from)
        if self.date_to:
            clauses.append("n.published_date <= %s")
            params.append(self.date_to)
        return (" AND ".join(clauses) or "TRUE"), params


@dataclass
class ChunkHit:
    chunk_id: str
    note_id: str
    title: str
    ticker: str | None
    company: str | None
    sector: str | None
    rating: str | None
    price_target: float | None
    currency: str | None
    analyst: str | None
    published_date: str
    heading: str | None
    content: str
    score: float = 0.0
    ranks: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_SELECT = """
SELECT c.chunk_id, c.note_id, n.title, n.ticker, n.company, n.sector, n.rating,
       n.price_target, n.currency, n.analyst, n.published_date, c.heading, c.content
FROM chunks c JOIN notes n USING (note_id)
"""


def _row_to_hit(row) -> ChunkHit:
    (chunk_id, note_id, title, ticker, company, sector, rating, pt, currency, analyst, date,
     heading, content) = row
    return ChunkHit(
        chunk_id=chunk_id, note_id=note_id, title=title, ticker=ticker, company=company,
        sector=sector, rating=rating, price_target=float(pt) if pt is not None else None,
        currency=currency, analyst=analyst, published_date=date.isoformat(), heading=heading,
        content=content,
    )


def dense_search(query: str, filters: SearchFilters, k: int) -> list[ChunkHit]:
    where, params = filters.sql()
    vec = embed_query(query)
    with get_pool().connection() as conn:
        rows = conn.execute(
            f"{_SELECT} WHERE {where} ORDER BY c.embedding <=> %s LIMIT %s",
            [*params, vec, k],
        ).fetchall()
    return [_row_to_hit(r) for r in rows]


def sparse_search(query: str, filters: SearchFilters, k: int) -> list[ChunkHit]:
    """Full-text leg. OR-joins the query terms so long natural-language questions still match."""
    where, params = filters.sql()
    with get_pool().connection() as conn:
        rows = conn.execute(
            f"""
            WITH q AS (
                SELECT to_tsquery('english', string_agg(quote_literal(lexeme), ' | ')) AS tsq
                FROM unnest(to_tsvector('english', %s))
            )
            {_SELECT}, q
            WHERE {where} AND q.tsq IS NOT NULL AND c.tsv @@ q.tsq
            ORDER BY ts_rank_cd(c.tsv, q.tsq) DESC
            LIMIT %s
            """,
            [query, *params, k],
        ).fetchall()
    return [_row_to_hit(r) for r in rows]


def rrf_fuse(rankings: dict[str, list[ChunkHit]], k: int = 60) -> list[ChunkHit]:
    """Reciprocal Rank Fusion: score = sum over legs of 1 / (k + rank)."""
    fused: dict[str, ChunkHit] = {}
    for leg, hits in rankings.items():
        for rank, hit in enumerate(hits, start=1):
            entry = fused.setdefault(hit.chunk_id, hit)
            entry.ranks[leg] = rank
            entry.score += 1.0 / (k + rank)
    return sorted(fused.values(), key=lambda h: h.score, reverse=True)


def hybrid_search(
    query: str,
    filters: SearchFilters | None = None,
    top_k: int | None = None,
    rerank: bool = True,
) -> list[ChunkHit]:
    filters = filters or SearchFilters()
    top_k = top_k or settings.top_k
    with span("hybrid_search", kind="retriever", inputs={"query": query, **asdict(filters)}) as s:
        with span("dense_search", kind="retriever", inputs={"query": query}):
            dense = dense_search(query, filters, settings.candidate_k)
        with span("sparse_search", kind="retriever", inputs={"query": query}):
            sparse = sparse_search(query, filters, settings.candidate_k)
        fused = rrf_fuse({"dense": dense, "sparse": sparse}, k=settings.rrf_k)

        reranker = get_reranker() if rerank else None
        if reranker and fused:
            candidates = fused[: settings.rerank_k]
            with span("rerank", kind="retriever", inputs={"query": query, "n": len(candidates)}):
                docs = [f"{h.title}\n{h.heading or ''}\n{h.content}" for h in candidates]
                for hit, score in zip(candidates, reranker.scores(query, docs)):
                    hit.ranks["rrf"] = fused.index(hit) + 1
                    hit.score = score
                results = sorted(candidates, key=lambda h: h.score, reverse=True)[:top_k]
        else:
            results = fused[:top_k]

        s.set_attribute("retrieval.dense_hits", len(dense))
        s.set_attribute("retrieval.sparse_hits", len(sparse))
        s.set_attribute(
            "output.value",
            ", ".join(f"{h.chunk_id}:{h.score:.3f}" for h in results),
        )
        return results


def get_note(note_id: str) -> dict[str, Any] | None:
    with span("get_note", kind="retriever", inputs={"note_id": note_id}):
        with get_pool().connection() as conn:
            row = conn.execute(
                """
                SELECT note_id, title, ticker, company, sector, rating, previous_rating,
                       price_target, currency, analyst, published_date, body
                FROM notes WHERE note_id = %s
                """,
                (note_id,),
            ).fetchone()
    if row is None:
        return None
    keys = ["note_id", "title", "ticker", "company", "sector", "rating", "previous_rating",
            "price_target", "currency", "analyst", "published_date", "body"]
    note = dict(zip(keys, row))
    note["published_date"] = note["published_date"].isoformat()
    if note["price_target"] is not None:
        note["price_target"] = float(note["price_target"])
    return note


def get_note_chunks(note_id: str) -> list[dict[str, Any]]:
    """A note's chunks in reading order; together they make up the whole body."""
    with get_pool().connection() as conn:
        rows = conn.execute(
            "SELECT chunk_id, heading, content FROM chunks WHERE note_id = %s ORDER BY chunk_index",
            (note_id,),
        ).fetchall()
    return [{"chunk_id": r[0], "heading": r[1], "content": r[2]} for r in rows]


def list_coverage() -> list[dict[str, Any]]:
    """Tickers and sectors in the store; used to ground the agent's filter extraction."""
    with get_pool().connection() as conn:
        rows = conn.execute(
            """
            SELECT ticker, company, sector, count(*), min(published_date), max(published_date)
            FROM notes GROUP BY ticker, company, sector ORDER BY sector, ticker NULLS FIRST
            """
        ).fetchall()
    return [
        {"ticker": t, "company": c, "sector": s, "notes": n,
         "first": f.isoformat(), "last": l.isoformat()}
        for t, c, s, n, f, l in rows
    ]
