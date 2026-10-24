"""LLM calls via OpenRouter's OpenAI-compatible Chat Completions API.

Two functions: ``stream_turn`` (one streamed agent turn, with tool calls) and ``parse`` (a
structured-output call for the eval judges). The default model is NVIDIA Nemotron 3.5 Super on
the free tier; any OpenRouter model with tool calling works.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Callable, TypeVar

from openai import AsyncOpenAI
from pydantic import BaseModel

from app.config import settings
from app.telemetry import span, to_attr

log = logging.getLogger(__name__)

MAX_TOKENS = 16000  # generous: reasoning models spend part of this on hidden reasoning
T = TypeVar("T", bound=BaseModel)


@dataclass
class ToolCall:
    id: str
    name: str
    input: Any
    parse_error: str | None = None  # set when the model's arguments aren't valid JSON


@dataclass
class Turn:
    """One model reply."""

    message: dict[str, Any]  # appended to the conversation exactly as received
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str = "stop"  # stop | tool_calls | length | content_filter


@lru_cache(maxsize=1)
def _client() -> AsyncOpenAI:
    if not settings.openrouter_api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set.")
    return AsyncOpenAI(
        base_url=settings.openrouter_base_url,
        api_key=settings.openrouter_api_key,
        max_retries=5,  # free models rate-limit at 20 req/min; the SDK backs off on 429
        default_headers={"X-Title": "Agentic Research Assistant"},
    )


async def stream_turn(messages: list[dict], system: str, tools: list[dict],
                      emit: Callable[[dict[str, Any]], None],
                      allow_tools: bool = True) -> Turn:
    """Stream one reply. Text deltas are emitted as they arrive; tool-call arguments arrive in
    fragments keyed by index and are assembled here. With ``allow_tools=False`` the model must
    answer in text (used when the step budget is spent)."""
    full = [{"role": "system", "content": system}, *messages]
    text_parts: list[str] = []
    calls: dict[int, dict[str, str]] = {}
    finish, usage = "stop", None

    with span("openrouter.chat", kind="llm", **{
        "gen_ai.system": "openrouter",
        "gen_ai.request.model": settings.openrouter_model,
        "gen_ai.input.messages": to_attr(full),
    }) as s:
        stream = await _client().chat.completions.create(
            model=settings.openrouter_model,
            messages=full,
            tools=tools,
            tool_choice="auto" if allow_tools else "none",
            max_tokens=MAX_TOKENS,
            stream=True,
            stream_options={"include_usage": True},
        )
        async for chunk in stream:
            usage = chunk.usage or usage
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            if choice.delta.content:
                text_parts.append(choice.delta.content)
                emit({"type": "text", "delta": choice.delta.content})
            for tc in choice.delta.tool_calls or []:
                slot = calls.setdefault(tc.index, {"id": "", "name": "", "arguments": ""})
                slot["id"] = tc.id or slot["id"]
                if tc.function and tc.function.name:
                    slot["name"] += tc.function.name
                    emit({"type": "tool_start", "name": slot["name"]})
                if tc.function and tc.function.arguments:
                    slot["arguments"] += tc.function.arguments
            finish = choice.finish_reason or finish

        text = "".join(text_parts)
        slots = [calls[i] for i in sorted(calls)]
        for slot in slots:
            slot["id"] = slot["id"] or f"call_{uuid.uuid4().hex[:12]}"
        tool_calls = [_to_tool_call(slot) for slot in slots]
        message: dict[str, Any] = {"role": "assistant", "content": text or None}
        if slots:
            message["tool_calls"] = [
                {"id": slot["id"], "type": "function",
                 "function": {"name": slot["name"], "arguments": slot["arguments"] or "{}"}}
                for slot in slots
            ]

        if usage:
            s.set_attribute("gen_ai.usage.input_tokens", usage.prompt_tokens or 0)
            s.set_attribute("gen_ai.usage.output_tokens", usage.completion_tokens or 0)
        s.set_attribute("llm.finish_reason", finish)
        s.set_attribute("gen_ai.output.messages", to_attr([message]))

    return Turn(message=message, text=text, tool_calls=tool_calls, finish_reason=finish)


def _to_tool_call(slot: dict[str, str]) -> ToolCall:
    try:
        return ToolCall(slot["id"], slot["name"], json.loads(slot["arguments"] or "{}"))
    except json.JSONDecodeError as exc:
        return ToolCall(slot["id"], slot["name"], slot["arguments"],
                        parse_error=f"arguments are not valid JSON: {exc}")


# --------------------------------------------------------------------------- judges

def _strict_schema(schema: dict) -> dict:
    """OpenAI-style strict JSON schema: every object closed, every property required."""
    if schema.get("type") == "object":
        schema["additionalProperties"] = False
        schema["required"] = list(schema.get("properties", {}))
        for prop in schema.get("properties", {}).values():
            _strict_schema(prop)
    if "items" in schema:
        _strict_schema(schema["items"])
    for sub in schema.get("$defs", {}).values():
        _strict_schema(sub)
    return schema


def _extract_json(text: str) -> str:
    """Models without strict structured output sometimes wrap JSON in prose or fences."""
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if fenced:
        return fenced.group(1)
    start, end = text.find("{"), text.rfind("}")
    return text[start:end + 1] if start != -1 and end > start else text


async def parse(prompt: str, schema: type[T]) -> T:
    """One structured-output call, validated against ``schema``; retried once on bad JSON."""
    schema_json = _strict_schema(schema.model_json_schema())
    last_error: Exception | None = None
    for _ in range(2):
        resp = await _client().chat.completions.create(
            model=settings.openrouter_judge_model,
            max_tokens=MAX_TOKENS,
            messages=[{"role": "user", "content": prompt + "\n\nRespond with JSON only."}],
            response_format={"type": "json_schema", "json_schema": {
                "name": schema.__name__, "strict": True, "schema": schema_json}},
        )
        try:
            return schema.model_validate_json(_extract_json(resp.choices[0].message.content or ""))
        except ValueError as exc:  # pydantic ValidationError subclasses ValueError
            log.warning("judge returned invalid JSON (finish_reason=%s); retrying",
                        resp.choices[0].finish_reason)
            last_error = exc
    raise RuntimeError(f"judge returned invalid JSON twice: {last_error}")
