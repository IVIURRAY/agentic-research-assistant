"""FastAPI service: SSE chat stream, feedback, and note lookup."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from contextlib import asynccontextmanager
from functools import lru_cache
from typing import Any, Literal

import openai
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from opentelemetry import trace
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from app.agent import cited_note_ids, graph, initial_state
from app.config import settings
from app.db import close_pool, get_pool, init_schema
from app.retrieval import get_note, list_coverage
from app.telemetry import current_trace_run_id, setup_telemetry, shutdown_telemetry, span, to_attr

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_schema()
    # Warm the local models so the first question isn't slow.
    from app.embeddings import embed_query
    from app.rerank import get_reranker

    await asyncio.to_thread(embed_query, "warmup")
    await asyncio.to_thread(get_reranker)
    yield
    close_pool()
    shutdown_telemetry()


app = FastAPI(title="Agentic Research Assistant", lifespan=lifespan)
setup_telemetry(app)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)


class Turn(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    history: list[Turn] = Field(default_factory=list)


class FeedbackRequest(BaseModel):
    run_id: str
    session_id: str | None = None
    score: Literal[1, -1]
    comment: str | None = None


def _user_error(exc: Exception) -> str:
    """Turn the common setup failures into messages a new user can act on."""
    if isinstance(exc, openai.AuthenticationError) or "OPENROUTER_API_KEY" in str(exc):
        return ("OpenRouter key is missing or invalid. Set OPENROUTER_API_KEY in .env "
                "and restart the API.")
    if isinstance(exc, openai.RateLimitError):
        return ("OpenRouter rate limit hit. Free models allow 20 requests/minute and 50/day "
                "(1000/day after buying $10 of credits). Wait, or switch OPENROUTER_MODEL.")
    if isinstance(exc, openai.NotFoundError):
        return f"OpenRouter doesn't recognise model {settings.openrouter_model!r}: {exc}"
    if isinstance(exc, openai.APIConnectionError):
        return "Could not reach OpenRouter. Check your network and OPENROUTER_BASE_URL."
    return f"{type(exc).__name__}: {exc}"


def _sse(event: str, data: Any) -> dict[str, str]:
    return {"event": event, "data": json.dumps(data, default=str)}


@app.post("/chat")
async def chat(req: ChatRequest):
    # LangSmith threads key off the *root* run's metadata; the root is the HTTP server span.
    trace.get_current_span().set_attribute("langsmith.metadata.session_id", req.session_id)

    async def events():
        with span(
            "research_assistant.chat",
            kind="chain",
            inputs={"question": req.message},
            **{
                "langsmith.metadata.session_id": req.session_id,
                "langsmith.trace.name": "research_assistant.chat",
            },
        ) as root:
            run_id = current_trace_run_id()
            yield _sse("run", {"run_id": run_id, "session_id": req.session_id})
            final: dict[str, Any] = {}
            try:
                async for part in graph.astream(
                    initial_state([t.model_dump() for t in req.history], req.message),
                    {"recursion_limit": 4 * settings.max_agent_steps + 4},
                    stream_mode=["custom", "values"],
                    version="v2",
                ):
                    if part["type"] == "custom":
                        ev = part["data"]
                        yield _sse(ev["type"], ev)
                    elif part["type"] == "values":
                        final = part["data"]
            except Exception as exc:  # surface to the UI, keep the trace
                log.exception("chat failed")
                root.record_exception(exc)
                yield _sse("error", {"message": _user_error(exc)})
                return

            answer = final.get("answer", "")
            cited = cited_note_ids(answer)
            root.set_attribute("output.value", to_attr({"answer": answer, "cited": cited}))
            yield _sse("done", {
                "run_id": run_id,
                "answer": answer,
                "cited": cited,
                "sources": final.get("sources", {}),
                "trajectory": final.get("trajectory", []),
                "steps": final.get("steps", 0),
            })

    return EventSourceResponse(events(), ping=15)


@lru_cache(maxsize=1)
def _langsmith() -> tuple[Any, Any]:
    """LangSmith client plus the UUID of the tracing project (LangSmith calls it session_id;
    unrelated to our chat session id). Feedback writes require it."""
    from langsmith import Client

    client = Client()
    project = client.create_project(project_name=settings.langsmith_project, upsert=True)
    return client, project.id


def _langsmith_feedback(fb: FeedbackRequest) -> None:
    if not settings.langsmith_api_key:
        return
    try:
        client, project_id = _langsmith()
        client.create_feedback(
            run_id=fb.run_id,
            trace_id=fb.run_id,
            session_id=project_id,
            key="user_thumbs",
            score=1 if fb.score > 0 else 0,
            comment=fb.comment,
        )
    except Exception:
        log.exception("failed to write LangSmith feedback")


@app.post("/feedback")
async def feedback(fb: FeedbackRequest):
    with get_pool().connection() as conn:
        conn.execute(
            "INSERT INTO feedback (run_id, session_id, score, comment) VALUES (%s, %s, %s, %s)",
            (fb.run_id, fb.session_id, fb.score, fb.comment),
        )
    asyncio.get_running_loop().run_in_executor(None, _langsmith_feedback, fb)
    return {"ok": True}


@app.get("/notes/{note_id}")
async def note(note_id: str):
    found = await asyncio.to_thread(get_note, note_id)
    if found is None:
        raise HTTPException(404, "note not found")
    return found


@app.get("/coverage")
async def coverage():
    return await asyncio.to_thread(list_coverage)


@app.get("/health")
async def health():
    with get_pool().connection() as conn:
        notes = conn.execute("SELECT count(*) FROM notes").fetchone()[0]
    return {"ok": True, "notes": notes, "model": settings.openrouter_model}
