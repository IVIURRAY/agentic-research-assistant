"""LangGraph agent: an LLM in a tool loop over search_notes / get_note.

    START -> agent --(tool_use)--> tools --> agent ... --(end_turn)--> END

The model is an OpenRouter model (default: NVIDIA Nemotron 3 Super, free) via ``app.llm``.
The graph state holds the Chat Completions message list;
assistant turns are appended exactly as returned and never edited, so history is append-only.
Nodes push UI events (text deltas, tool calls, sources) through LangGraph's custom stream writer;
the API turns those into SSE.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
import re
from functools import lru_cache
from typing import Any, TypedDict

from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph

from app.config import settings
from app.llm import ToolResult, get_provider
from app.retrieval import list_coverage
from app.telemetry import span, to_attr
from app.tools import TOOLS, ToolError, run_tool

log = logging.getLogger(__name__)

SYSTEM_TEMPLATE = """You are a research assistant for an equity research team. You answer questions \
using only the firm's research notes, which you reach through the search_notes and get_note tools.

How to work:
- Always search before answering; never answer from general knowledge about these companies.
- Turn the question into filters, every time: if it names a covered company, always pass its \
ticker; if it is about a sector, pass sector; if it is about the house view or top picks, pass \
sector="Strategy"; "since Q1", "in April", "this year" -> date_from/date_to. Today is {today}.
- For questions about change over time or comparisons, search each company or period separately \
and compare ratings, price targets and theses across dates.
- Use get_note when a chunk lacks the detail you need.
- If the notes do not contain the answer, say so plainly.

How to answer:
- Lead with the direct answer, then the supporting detail. Be concise.
- Every sentence that states a fact needs a citation, including the opening summary sentence.
- Cite every factual claim with the note_id in plain ASCII square brackets right after it, e.g. \
"We upgraded to Buy [asml-2026-04-16]." Use the note_id exactly as given in the tool results \
(no section numbers or other suffixes), and only cite note_ids the tools returned.
- State dates, ratings and price targets exactly as written in the notes.

Coverage in the note store (ticker | company | sector | notes | date range):
{coverage}"""


class AgentState(TypedDict, total=False):
    system: str
    messages: list[dict[str, Any]]
    pending_tool_calls: list[dict[str, Any]]
    steps: int
    trajectory: list[dict[str, Any]]
    sources: dict[str, dict[str, Any]]
    answer: str
    stop_reason: str


@lru_cache(maxsize=1)
def _coverage_text() -> str:
    rows = list_coverage()
    return "\n".join(
        f"- {r['ticker'] or '(sector/strategy)'} | {r['company'] or '-'} | {r['sector']} | "
        f"{r['notes']} | {r['first']} to {r['last']}"
        for r in rows
    )


def system_prompt(today: dt.date | None = None) -> str:
    return SYSTEM_TEMPLATE.format(
        today=(today or dt.date.today()).isoformat(), coverage=_coverage_text()
    )


def _emit(event: dict[str, Any]) -> None:
    try:
        get_stream_writer()(event)
    except RuntimeError:
        pass  # invoked outside a streaming context (e.g. evals)


async def agent_node(state: AgentState) -> AgentState:
    steps = state.get("steps", 0) + 1
    provider = get_provider()
    with span("agent", kind="chain", inputs={"step": steps}):
        turn = await provider.stream_turn(
            state["messages"], state.get("system") or system_prompt(), TOOLS, _emit
        )

    messages = [*state["messages"], turn.assistant_message]
    answer = state.get("answer", "")
    if turn.text:
        answer = f"{answer}\n\n{turn.text}".strip() if answer else turn.text
    pending = [{"id": c.id, "name": c.name, "input": c.input, "parse_error": c.parse_error}
               for c in turn.tool_calls]
    update = {**state, "messages": messages, "steps": steps, "answer": answer,
              "pending_tool_calls": pending, "stop_reason": turn.stop_reason}

    if turn.stop_reason == "refusal":
        _emit({"type": "text", "delta": "\n\nI can't help with that request."})
    elif turn.stop_reason == "max_tokens" and pending:
        # A truncated tool input can parse as a valid partial object; never run it.
        _emit({"type": "error", "message": "Response hit max_tokens mid tool call."})
    return update


async def tools_node(state: AgentState) -> AgentState:
    provider = get_provider()
    calls = state.get("pending_tool_calls", [])
    trajectory = list(state.get("trajectory", []))
    sources = dict(state.get("sources", {}))

    async def run_one(call: dict[str, Any]) -> ToolResult:
        name, raw, cid = call["name"], call.get("input"), call["id"]
        trajectory.append({"name": name, "input": raw})
        _emit({"type": "tool_call", "id": cid, "name": name,
               "input": raw if isinstance(raw, dict) else {}})
        with span(f"tool.{name}", kind="tool", inputs=raw, **{"gen_ai.tool.name": name}) as s:
            try:
                if call.get("parse_error"):
                    raise ToolError(call["parse_error"])
                text, found = await asyncio.to_thread(run_tool, name, raw)
            except ToolError as exc:
                s.set_attribute("output.value", str(exc))
                _emit({"type": "tool_result", "id": cid, "name": name, "error": str(exc)})
                return ToolResult(cid, str(exc), is_error=True)
            s.set_attribute("output.value", to_attr(text))
        for src in found:
            sources.setdefault(src["note_id"], {k: v for k, v in src.items()
                                                if k not in {"content", "chunk_id", "heading",
                                                             "score", "ranks", "body"}})
            sources[src["note_id"]].setdefault("chunks", [])
            if not any(c["chunk_id"] == src["chunk_id"] for c in sources[src["note_id"]]["chunks"]):
                sources[src["note_id"]]["chunks"].append(
                    {"chunk_id": src["chunk_id"], "heading": src.get("heading"),
                     "content": src["content"], "score": src.get("score")}
                )
        _emit({
            "type": "tool_result", "id": cid, "name": name,
            "results": [{"note_id": s["note_id"], "chunk_id": s["chunk_id"]} for s in found],
        })
        return ToolResult(cid, text)

    # Parallel tool calls run concurrently; results go back together.
    results = await asyncio.gather(*(run_one(c) for c in calls))
    _emit({"type": "sources", "sources": sources})

    messages = [*state["messages"], *provider.tool_result_messages(list(results))]
    if state.get("steps", 0) >= settings.max_agent_steps:
        messages.append(provider.system_note(
            "Tool budget reached. Answer now from the evidence gathered so far, "
            "without calling more tools, and say what is missing if anything."
        ))
    return {**state, "messages": messages, "trajectory": trajectory, "sources": sources,
            "pending_tool_calls": []}


def route_after_agent(state: AgentState) -> str:
    if state.get("stop_reason") == "tool_use" and state.get("steps", 0) <= settings.max_agent_steps:
        return "tools"
    if state.get("stop_reason") == "pause_turn":
        return "agent"
    return END


def build_graph():
    g = StateGraph(AgentState)
    g.add_node("agent", agent_node)
    g.add_node("tools", tools_node)
    g.add_edge(START, "agent")
    g.add_conditional_edges("agent", route_after_agent, {"tools": "tools", "agent": "agent", END: END})
    g.add_edge("tools", "agent")
    return g.compile()


graph = build_graph()


def initial_state(history: list[dict[str, str]], question: str) -> AgentState:
    """History is prior turns as plain text; the new question is appended last."""
    messages = [{"role": m["role"], "content": m["content"]} for m in history if m.get("content")]
    messages.append({"role": "user", "content": question})
    return {"messages": messages, "steps": 0, "trajectory": [], "sources": {}, "answer": "",
            "pending_tool_calls": [], "system": system_prompt()}


async def run_agent(question: str, history: list[dict[str, str]] | None = None) -> AgentState:
    """Non-streaming entry point (evals, scripts)."""
    with span("research_assistant.chat", kind="chain", inputs={"question": question}):
        return await graph.ainvoke(initial_state(history or [], question),
                                   {"recursion_limit": 4 * settings.max_agent_steps + 4})


# A note id, optionally with a "#<chunk>" suffix some models copy from chunk ids.
_NOTE_ID = r"[a-z0-9][a-z0-9\-]*-[a-z0-9\-]+(?:#\d+)?"
# Square brackets, or the full-width 【】 some models (e.g. Nemotron) use for citations.
CITATION_RE = re.compile(rf"[\[【]\s*({_NOTE_ID}(?:\s*[,;]\s*{_NOTE_ID})*)\s*[\]】]")


def cited_note_ids(answer: str) -> list[str]:
    seen: list[str] = []
    for m in CITATION_RE.finditer(answer):
        for nid in re.split(r"[,;]", m.group(1)):
            nid = nid.strip().split("#", 1)[0]
            if nid and nid not in seen:
                seen.append(nid)
    return seen

