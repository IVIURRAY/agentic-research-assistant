"""LangGraph agent: a ReAct loop (reason, act, observe) over search_notes / get_note.

    START -> agent --(reply has tool calls)--> tools --> agent ... --(no tool calls)--> END

The model decides when it has enough evidence, by replying without tool calls; the graph only
routes on that. After MAX_AGENT_STEPS tool rounds, the next call disables tools, so the model
must answer from what it has.

The state holds the Chat Completions message list. Every message is appended exactly as
received and never edited. Nodes push UI events (text deltas, tool calls, sources) through
LangGraph's custom stream writer; the API turns those into SSE.
"""

from __future__ import annotations

import asyncio
import dataclasses
import datetime as dt
import logging
import re
from functools import lru_cache
from typing import Any, TypedDict

from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph

from app import llm
from app.config import settings
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
    pending_tool_calls: list[dict[str, Any]]  # tool calls from the latest reply, not yet run
    steps: int  # model calls so far
    trajectory: list[dict[str, Any]]  # every tool call made, for the UI and the evals
    sources: dict[str, dict[str, Any]]  # note_id -> metadata + retrieved chunks, for citations
    answer: str  # text of the latest reply
    finish_reason: str


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
    budget_spent = steps > settings.max_agent_steps
    with span("agent", kind="chain", inputs={"step": steps}):
        turn = await llm.stream_turn(state["messages"], state["system"], TOOLS, _emit,
                                     allow_tools=not budget_spent)

    calls = turn.tool_calls
    if turn.finish_reason == "length" and calls:
        # Truncated tool arguments can still parse as a valid partial object; never run them.
        _emit({"type": "error", "message": "Response hit max_tokens mid tool call."})
        calls = []
    elif turn.finish_reason == "content_filter":
        _emit({"type": "text", "delta": "\n\nI can't help with that request."})

    return {**state,
            "messages": [*state["messages"], turn.message],
            "steps": steps,
            "answer": turn.text,
            "pending_tool_calls": [dataclasses.asdict(c) for c in calls],
            "finish_reason": turn.finish_reason}


def _add_sources(sources: dict[str, dict[str, Any]], found: list[dict[str, Any]]) -> None:
    """Group retrieved chunks by note, for the citations panel."""
    for src in found:
        note = sources.setdefault(src["note_id"], {
            k: v for k, v in src.items()
            if k not in {"content", "chunk_id", "heading", "score", "ranks", "body"}
        })
        chunks = note.setdefault("chunks", [])
        if all(c["chunk_id"] != src["chunk_id"] for c in chunks):
            chunks.append({"chunk_id": src["chunk_id"], "heading": src.get("heading"),
                           "content": src["content"], "score": src.get("score")})


async def tools_node(state: AgentState) -> AgentState:
    trajectory = list(state.get("trajectory", []))
    sources = dict(state.get("sources", {}))

    async def run_one(call: dict[str, Any]) -> dict[str, Any]:
        name, args, cid = call["name"], call["input"], call["id"]
        trajectory.append({"name": name, "input": args})
        _emit({"type": "tool_call", "id": cid, "name": name,
               "input": args if isinstance(args, dict) else {}})
        with span(f"tool.{name}", kind="tool", inputs=args, **{"gen_ai.tool.name": name}) as s:
            try:
                if call["parse_error"]:
                    raise ToolError(call["parse_error"])
                text, found = await asyncio.to_thread(run_tool, name, args)
            except ToolError as exc:
                # Errors go back to the model as the tool result, so it can correct itself.
                s.set_attribute("output.value", str(exc))
                _emit({"type": "tool_result", "id": cid, "name": name, "error": str(exc)})
                return {"role": "tool", "tool_call_id": cid, "content": f"ERROR: {exc}"}
            s.set_attribute("output.value", to_attr(text))
        _add_sources(sources, found)
        _emit({"type": "tool_result", "id": cid, "name": name,
               "results": [{"note_id": f["note_id"], "chunk_id": f["chunk_id"]} for f in found]})
        return {"role": "tool", "tool_call_id": cid, "content": text}

    # Parallel tool calls run concurrently; every result goes back before the next model call.
    results = await asyncio.gather(*(run_one(c) for c in state["pending_tool_calls"]))
    _emit({"type": "sources", "sources": sources})
    return {**state, "messages": [*state["messages"], *results], "trajectory": trajectory,
            "sources": sources, "pending_tool_calls": []}


def route_after_agent(state: AgentState) -> str:
    """Tool calls in the reply -> run them; none -> the model has answered."""
    if state.get("pending_tool_calls") and state.get("steps", 0) <= settings.max_agent_steps:
        return "tools"
    return END


def build_graph():
    g = StateGraph(AgentState)
    g.add_node("agent", agent_node)
    g.add_node("tools", tools_node)
    g.add_edge(START, "agent")
    g.add_conditional_edges("agent", route_after_agent, {"tools": "tools", END: END})
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

