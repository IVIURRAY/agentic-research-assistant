"""End-to-end through the real graph, tools, Postgres and SSE endpoint, with the LLM scripted
as an OpenRouter (OpenAI-compatible) stream.

Needs the database up and ingested (docker compose up -d postgres && python -m app.ingest).
Skipped automatically when the database is unreachable.
"""

from __future__ import annotations

import json

import psycopg
import pytest
from openai.types.chat import ChatCompletionChunk

from app import agent
from app.config import settings


def _db_ready() -> bool:
    try:
        with psycopg.connect(settings.database_url, connect_timeout=2) as conn:
            return conn.execute("SELECT count(*) FROM notes").fetchone()[0] > 0
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _db_ready(), reason="database not available/ingested")


def _chunk(delta: dict, finish: str | None = None, usage: dict | None = None) -> ChatCompletionChunk:
    return ChatCompletionChunk.model_validate({
        "id": "gen-1", "object": "chat.completion.chunk", "created": 0,
        "model": "nvidia/nemotron-3-super-120b-a12b:free",
        "choices": [] if usage else [{"index": 0, "delta": delta, "finish_reason": finish}],
        **({"usage": usage} if usage else {}),
    })


class FakeOpenRouter:
    """Scripted OpenAI-compatible stream: a tool call whose JSON arrives in fragments, then an
    answer. Mirrors how OpenRouter streams tool calls (index-keyed argument deltas).
    With ``always_search`` it keeps calling tools until tools are disabled."""

    def __init__(self, always_search: bool = False):
        self.requests: list[dict] = []
        self.always_search = always_search
        self.chat = self
        self.completions = self

    async def create(self, **kwargs):
        self.requests.append(kwargs)
        answered_tool = kwargs["messages"][-1]["role"] == "tool"
        wants_tool = (self.always_search or not answered_tool) and kwargs["tool_choice"] != "none"
        if wants_tool:
            chunks = [
                # Some models narrate before calling a tool; that text must not be the answer.
                _chunk({"role": "assistant", "content": "Let me search the notes. "}),
                _chunk({"tool_calls": [{"index": 0, "id": f"call_{len(self.requests)}",
                        "type": "function", "function": {"name": "search_notes",
                                                         "arguments": '{"query": "ASML rating'}}]}),
                _chunk({"tool_calls": [{"index": 0, "function": {
                        "arguments": ' changes", "ticker": "ASML"}'}}]}),
                _chunk({}, finish="tool_calls"),
            ]
        else:
            # Mixes both citation styles seen from real models: [id] and 【id#chunk】.
            chunks = [
                _chunk({"role": "assistant", "content": "We upgraded ASML to Buy in April "}),
                _chunk({"content": "[asml-2026-04-16] after holding it at Hold in January "}),
                _chunk({"content": "【asml-2026-01-14#0】."}),
                _chunk({}, finish="stop"),
            ]
        chunks.append(_chunk({}, usage={"prompt_tokens": 10, "completion_tokens": 5,
                                        "total_tokens": 15}))

        async def gen():
            for c in chunks:
                yield c
        return gen()


def _use_fake(monkeypatch, fake: FakeOpenRouter) -> FakeOpenRouter:
    from app import llm

    monkeypatch.setattr(llm, "_client", lambda: fake)
    return fake


@pytest.fixture
def fake_openrouter(monkeypatch):
    return _use_fake(monkeypatch, FakeOpenRouter())


async def test_openrouter_tool_loop(fake_openrouter):
    state = await agent.run_agent("What's our ASML rating?")
    assert state["finish_reason"] == "stop"
    assert state["answer"].startswith("We upgraded")  # the final reply only, not the narration
    assert state["trajectory"] == [
        {"name": "search_notes", "input": {"query": "ASML rating changes", "ticker": "ASML"}}
    ]
    assert agent.cited_note_ids(state["answer"]) == ["asml-2026-04-16", "asml-2026-01-14"]
    assert "asml-2026-04-16" in state["sources"]

    first, second = fake_openrouter.requests
    assert first["messages"][0]["role"] == "system"
    assert "ASML" in first["messages"][0]["content"]  # coverage list is in the prompt
    assert first["tools"][0]["function"]["name"] == "search_notes"
    assert first["tool_choice"] == "auto"
    # Assistant tool-call turn is echoed back, followed by a role=tool result.
    assistant, tool = second["messages"][-2:]
    assert assistant["tool_calls"][0]["function"]["arguments"] == (
        '{"query": "ASML rating changes", "ticker": "ASML"}')
    assert tool["role"] == "tool" and tool["tool_call_id"] == "call_1"
    assert "asml-2026-04-16" in tool["content"]
    # History is append-only: the second request starts with the first request's messages.
    assert second["messages"][: len(first["messages"])] == first["messages"]


async def test_step_budget_forces_an_answer(monkeypatch):
    """A model that never stops searching gets tools disabled after MAX_AGENT_STEPS."""
    import dataclasses

    fake = _use_fake(monkeypatch, FakeOpenRouter(always_search=True))
    monkeypatch.setattr(agent, "settings", dataclasses.replace(settings, max_agent_steps=2))
    state = await agent.run_agent("What's our ASML rating?")

    assert [r["tool_choice"] for r in fake.requests] == ["auto", "auto", "none"]
    assert len(state["trajectory"]) == 2
    assert agent.cited_note_ids(state["answer"]) == ["asml-2026-04-16", "asml-2026-01-14"]


def test_sse_endpoint(fake_openrouter):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        events = []
        with client.stream("POST", "/chat", json={"message": "ASML view?", "session_id": "s1"}) as r:
            assert r.status_code == 200
            event = None
            for line in r.iter_lines():
                if line.startswith("event:"):
                    event = line.split(":", 1)[1].strip()
                elif line.startswith("data:") and event:
                    events.append((event, json.loads(line.split(":", 1)[1])))
        kinds = [e for e, _ in events]
        assert kinds[0] == "run"
        assert {"tool_start", "tool_call", "tool_result", "sources", "text", "done"} <= set(kinds)
        done = dict(events)["done"]
        assert done["cited"] == ["asml-2026-04-16", "asml-2026-01-14"]
        assert "asml-2026-04-16" in done["sources"]

        fb = client.post("/feedback", json={"run_id": "test-r1", "session_id": "s1", "score": 1})
        assert fb.json() == {"ok": True}
        with psycopg.connect(settings.database_url) as conn:
            conn.execute("DELETE FROM feedback WHERE run_id = 'test-r1'")
        note = client.get("/notes/asml-2026-04-16").json()
        assert note["rating"] == "Buy"
        # Chunks come back in reading order and together cover the body.
        assert [c["chunk_id"] for c in note["chunks"]] == [
            f"asml-2026-04-16#{i}" for i in range(len(note["chunks"]))]
        assert all(c["content"] in note["body"] for c in note["chunks"])
        assert client.get("/notes/nope").status_code == 404
