"""The agent's two tools. Inputs are validated with pydantic before anything runs."""

from __future__ import annotations

import datetime as dt
import json
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator

from app.retrieval import SearchFilters, get_note, hybrid_search

TOOLS: list[dict[str, Any]] = [
    {
        "name": "search_notes",
        "description": (
            "Hybrid (semantic + keyword) search over the firm's equity research notes. Returns the "
            "most relevant chunks with their note_id, title, ticker, date, rating and price target. "
            "Extract filters from the question whenever it names a company/ticker, a sector, or a "
            "time window - filters are applied before ranking, so they sharply improve precision. "
            "Call it several times for multi-part or over-time questions (e.g. once per company, "
            "or once per period)."
        ),
        "eager_input_streaming": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "What to look for, in natural language.",
                },
                "ticker": {
                    "type": "string",
                    "description": "Restrict to one covered ticker, e.g. ASML, NVDA, HSBA.",
                },
                "sector": {
                    "type": "string",
                    "description": "Restrict to one sector, e.g. Semiconductors, Banks.",
                },
                "date_from": {
                    "type": "string",
                    "description": "Earliest publish date, inclusive, YYYY-MM-DD.",
                },
                "date_to": {
                    "type": "string",
                    "description": "Latest publish date, inclusive, YYYY-MM-DD.",
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_note",
        "description": (
            "Fetch the full text and metadata of one research note by note_id. Use it when a "
            "search chunk is not enough, e.g. to read a note's full thesis, valuation or risks."
        ),
        "eager_input_streaming": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "note_id": {"type": "string", "description": "A note_id from search results."},
            },
            "required": ["note_id"],
            "additionalProperties": False,
        },
    },
]


class SearchNotesInput(BaseModel):
    model_config = {"extra": "forbid"}

    query: str = Field(min_length=1)
    ticker: str | None = None
    sector: str | None = None
    date_from: dt.date | None = None
    date_to: dt.date | None = None

    @field_validator("ticker", "sector", mode="before")
    @classmethod
    def _blank_to_none(cls, v):
        return v.strip() or None if isinstance(v, str) else v


class GetNoteInput(BaseModel):
    model_config = {"extra": "forbid"}

    note_id: str = Field(min_length=1)


class ToolError(Exception):
    pass


def _fmt_pt(pt: float | None, ccy: str | None) -> str:
    if pt is None:
        return "n/a"
    return f"{pt:,.0f} {ccy or ''}".strip()


def run_tool(name: str, raw_input: Any) -> tuple[str, list[dict[str, Any]]]:
    """Execute a tool. Returns (text for the model, source records for the UI citations panel)."""
    try:
        if name == "search_notes":
            args = SearchNotesInput.model_validate(raw_input)
            hits = hybrid_search(
                args.query,
                SearchFilters(args.ticker, args.sector, args.date_from, args.date_to),
            )
            if not hits:
                return "No matching notes. Try a broader query or fewer filters.", []
            blocks = []
            for h in hits:
                blocks.append(
                    f"<result note_id=\"{h.note_id}\">\n"
                    f"title: {h.title}\n"
                    f"ticker: {h.ticker or '-'} | sector: {h.sector or '-'} | "
                    f"date: {h.published_date} | rating: {h.rating or '-'} | "
                    f"price target: {_fmt_pt(h.price_target, h.currency)} | "
                    f"analyst: {h.analyst or '-'}\n"
                    f"section: {h.heading or '-'}\n"
                    f"{h.content}\n</result>"
                )
            return "\n\n".join(blocks), [h.to_dict() for h in hits]

        if name == "get_note":
            args = GetNoteInput.model_validate(raw_input)
            note = get_note(args.note_id)
            if note is None:
                raise ToolError(f"No note with note_id {args.note_id!r}.")
            meta = {k: v for k, v in note.items() if k != "body"}
            text = f"<note note_id=\"{note['note_id']}\">\n{json.dumps(meta)}\n\n{note['body']}\n</note>"
            source = {**meta, "chunk_id": f"{note['note_id']}#full", "heading": None,
                      "content": note["body"], "score": None}
            return text, [source]

        raise ToolError(f"Unknown tool {name!r}.")
    except ValidationError as exc:
        raise ToolError(f"Invalid input for {name}: {exc.errors(include_url=False)}") from exc
