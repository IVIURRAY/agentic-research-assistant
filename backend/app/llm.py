"""LLM client: OpenRouter's OpenAI-compatible Chat Completions API.

The default model is NVIDIA Nemotron 3 Super (free tier); any OpenRouter model that supports tool
calling works for the agent, and one that supports structured outputs works for the judge.
Messages in the graph state stay in the Chat Completions shape, and assistant turns are appended
exactly as returned, so the history is append-only.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Callable, TypeVar

from pydantic import BaseModel

from app.config import settings
from app.telemetry import span, to_attr

log = logging.getLogger(__name__)

Emit = Callable[[dict[str, Any]], None]
T = TypeVar("T", bound=BaseModel)


@dataclass
class ToolCall:
    id: str
    name: str
    input: Any
    parse_error: str | None = None  # set when the model emitted arguments that aren't JSON


@dataclass
class Turn:
    """One model response, normalised for the graph."""

    assistant_message: dict[str, Any]  # provider-native, appended to history unchanged
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    # normalised: tool_use | end_turn | max_tokens | refusal | pause_turn
    stop_reason: str = "end_turn"


@dataclass
class ToolResult:
    tool_call_id: str
    content: str
    is_error: bool = False


def _llm_span(provider: str, model: str, messages: list[dict]):
    return span(
        f"{provider}.chat",
        kind="llm",
        **{
            "gen_ai.system": provider,
            "gen_ai.operation.name": "chat",
            "gen_ai.request.model": model,
            "gen_ai.input.messages": to_attr(messages),
        },
    )


# --------------------------------------------------------------------------- OpenRouter

def _openai_tools(tools: list[dict]) -> list[dict]:
    return [{"type": "function", "function": {
        "name": t["name"], "description": t["description"], "parameters": t["input_schema"],
    }} for t in tools]


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


class OpenRouterProvider:
    name = "openrouter"
    MAX_TOKENS = 16000

    def __init__(self) -> None:
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(
            base_url=settings.openrouter_base_url,
            api_key=settings.openrouter_api_key,
            max_retries=5,  # free models rate-limit at 20 req/min; the SDK backs off on 429
            default_headers={"X-Title": "Agentic Research Assistant"},
        )
        self.model = settings.openrouter_model

    async def stream_turn(self, messages, system, tools, emit) -> Turn:
        full = [{"role": "system", "content": system}, *messages]
        text_parts: list[str] = []
        calls: dict[int, dict[str, str]] = {}
        finish = None
        usage = None
        with _llm_span(self.name, self.model, full) as s:
            stream = await self._client.chat.completions.create(
                model=self.model,
                messages=full,
                tools=_openai_tools(tools),
                tool_choice="auto",
                max_tokens=self.MAX_TOKENS,
                stream=True,
                stream_options={"include_usage": True},
            )
            async for chunk in stream:
                if chunk.usage:
                    usage = chunk.usage
                if not chunk.choices:
                    continue
                choice = chunk.choices[0]
                delta = choice.delta
                if delta.content:
                    text_parts.append(delta.content)
                    emit({"type": "text", "delta": delta.content})
                for tc in delta.tool_calls or []:
                    slot = calls.setdefault(tc.index, {"id": "", "name": "", "arguments": ""})
                    if tc.id:
                        slot["id"] = tc.id
                    if tc.function and tc.function.name:
                        slot["name"] += tc.function.name
                        emit({"type": "tool_start", "name": slot["name"]})
                    if tc.function and tc.function.arguments:
                        slot["arguments"] += tc.function.arguments
                if choice.finish_reason:
                    finish = choice.finish_reason

            text = "".join(text_parts)
            tool_calls: list[ToolCall] = []
            native_calls = []
            for idx in sorted(calls):
                c = calls[idx]
                c["id"] = c["id"] or f"call_{uuid.uuid4().hex[:12]}"
                native_calls.append({"id": c["id"], "type": "function",
                                     "function": {"name": c["name"],
                                                  "arguments": c["arguments"] or "{}"}})
                try:
                    args = json.loads(c["arguments"] or "{}")
                    tool_calls.append(ToolCall(c["id"], c["name"], args))
                except json.JSONDecodeError as exc:
                    tool_calls.append(ToolCall(c["id"], c["name"], c["arguments"],
                                               parse_error=f"arguments are not valid JSON: {exc}"))

            assistant: dict[str, Any] = {"role": "assistant", "content": text or None}
            if native_calls:
                assistant["tool_calls"] = native_calls

            stop = {"tool_calls": "tool_use", "length": "max_tokens",
                    "content_filter": "refusal"}.get(finish or "", "end_turn")
            if tool_calls and stop == "end_turn":
                stop = "tool_use"  # some providers report "stop" alongside tool calls

            if usage:
                s.set_attribute("gen_ai.usage.input_tokens", usage.prompt_tokens or 0)
                s.set_attribute("gen_ai.usage.output_tokens", usage.completion_tokens or 0)
            s.set_attribute("gen_ai.response.model", self.model)
            s.set_attribute("llm.stop_reason", finish or "")
            s.set_attribute("gen_ai.output.messages", to_attr([assistant]))

        return Turn(assistant_message=assistant, text=text, tool_calls=tool_calls,
                    stop_reason=stop)

    def tool_result_messages(self, results):
        return [{"role": "tool", "tool_call_id": r.tool_call_id,
                 "content": f"ERROR: {r.content}" if r.is_error else r.content}
                for r in results]

    def system_note(self, text):
        return {"role": "system", "content": text}

    async def parse(self, prompt, schema, model=None):
        schema_json = _strict_schema(schema.model_json_schema())
        last_error: Exception | None = None
        for _ in range(2):  # one retry: free models occasionally return malformed JSON
            # Reasoning models spend part of max_tokens on hidden reasoning, so leave plenty
            # of room or the JSON gets cut off mid-string.
            resp = await self._client.chat.completions.create(
                model=model or settings.openrouter_judge_model,
                max_tokens=self.MAX_TOKENS,
                messages=[{"role": "user", "content": prompt + "\n\nRespond with JSON only."}],
                response_format={"type": "json_schema", "json_schema": {
                    "name": schema.__name__, "strict": True, "schema": schema_json}},
            )
            content = resp.choices[0].message.content or ""
            try:
                return schema.model_validate_json(_extract_json(content))
            except ValueError as exc:  # pydantic ValidationError subclasses ValueError
                finish = resp.choices[0].finish_reason
                log.warning("judge returned invalid JSON (finish_reason=%s); retrying", finish)
                last_error = exc
        raise RuntimeError(f"judge returned invalid JSON twice: {last_error}")


# --------------------------------------------------------------------------- selection

@lru_cache(maxsize=1)
def get_provider() -> OpenRouterProvider:
    if not settings.openrouter_api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set.")
    return OpenRouterProvider()
