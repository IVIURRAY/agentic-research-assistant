"""OpenTelemetry setup. Spans go to any OTLP endpoint; by default LangSmith's.

Every request produces one trace: HTTP span -> chat root -> graph nodes -> LLM / tool / retrieval
spans. The root carries ``langsmith.metadata.session_id`` so LangSmith groups a conversation into
a thread.

``LangSmithIdProcessor`` stamps each span with a deterministic LangSmith run UUID (and the matching
trace id / dotted order). That lets the API hand the root run id to the UI, so thumbs up/down can be
written back as LangSmith feedback on exactly that trace.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import threading
import uuid
from contextlib import contextmanager
from typing import Any, Iterator

from opentelemetry import trace
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import ReadableSpan, Span, SpanProcessor, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Status, StatusCode

from app.config import settings

log = logging.getLogger(__name__)

tracer = trace.get_tracer("research-assistant")

_MAX_ATTR_CHARS = 16_000


def run_id_for(trace_id: int, span_id: int) -> uuid.UUID:
    """Deterministic UUID for a span: 8 bytes of trace id + the 8-byte span id."""
    return uuid.UUID(bytes=trace_id.to_bytes(16, "big")[:8] + span_id.to_bytes(8, "big"))


def _ts(ns: int) -> str:
    return dt.datetime.fromtimestamp(ns / 1e9, tz=dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


class LangSmithIdProcessor(SpanProcessor):
    """Assign LangSmith run ids/dotted orders that mirror the OTel span tree."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # trace_id -> {"root": uuid, "dotted": {span_id: dotted_order}}
        self._traces: dict[int, dict[str, Any]] = {}

    def on_start(self, span: Span, parent_context=None) -> None:
        ctx = span.get_span_context()
        rid = run_id_for(ctx.trace_id, ctx.span_id)
        stamp = f"{_ts(span.start_time or 0)}{rid}"
        parent = span.parent
        with self._lock:
            entry = self._traces.get(ctx.trace_id)
            if parent is None or entry is None or parent.span_id not in entry["dotted"]:
                if parent is not None:
                    return  # remote/unknown parent: let LangSmith derive ids itself
                entry = {"root": rid, "dotted": {}}
                self._traces[ctx.trace_id] = entry
                dotted = stamp
            else:
                dotted = f"{entry['dotted'][parent.span_id]}.{stamp}"
                span.set_attribute(
                    "langsmith.span.parent_id", str(run_id_for(ctx.trace_id, parent.span_id))
                )
            entry["dotted"][ctx.span_id] = dotted
        span.set_attribute("langsmith.trace.id", str(entry["root"]))
        span.set_attribute("langsmith.span.id", str(rid))
        span.set_attribute("langsmith.span.dotted_order", dotted)

    def root_run_id(self, trace_id: int) -> uuid.UUID | None:
        with self._lock:
            entry = self._traces.get(trace_id)
            return entry["root"] if entry else None

    def on_end(self, span: ReadableSpan) -> None:
        if span.parent is None:
            with self._lock:
                self._traces.pop(span.context.trace_id, None)

    def shutdown(self) -> None:
        pass

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True


_provider: TracerProvider | None = None
_ids = LangSmithIdProcessor()


def setup_telemetry(app=None) -> None:
    """Install the tracer provider. Exporter config:

    * ``OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`` / ``OTEL_EXPORTER_OTLP_HEADERS`` if set (Phoenix,
      Datadog, a collector...), otherwise
    * LangSmith's OTLP endpoint when ``LANGSMITH_API_KEY`` is set, otherwise
    * no exporter (spans are created but dropped).
    """
    global _provider
    if _provider is not None or not settings.otel_enabled:
        return
    import os

    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

    provider = TracerProvider(resource=Resource.create({SERVICE_NAME: settings.service_name}))
    provider.add_span_processor(_ids)

    exporter = None
    if os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT") or os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"):
        exporter = OTLPSpanExporter()
    elif settings.langsmith_api_key:
        exporter = OTLPSpanExporter(
            endpoint=f"{settings.langsmith_endpoint.rstrip('/')}/otel/v1/traces",
            headers={
                "x-api-key": settings.langsmith_api_key,
                "Langsmith-Project": settings.langsmith_project,
            },
        )
    if exporter is not None:
        provider.add_span_processor(BatchSpanProcessor(exporter))
        log.info("OTel exporter enabled")
    else:
        log.info("OTel: no exporter configured; spans are not exported")

    trace.set_tracer_provider(provider)
    _provider = provider

    if app is not None:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(
            app,
            tracer_provider=provider, excluded_urls="health",
            exclude_spans=["send", "receive"],  # no per-SSE-chunk spans
        )


def shutdown_telemetry() -> None:
    if _provider is not None:
        _provider.shutdown()


def to_attr(value: Any) -> str:
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    return text if len(text) <= _MAX_ATTR_CHARS else text[:_MAX_ATTR_CHARS] + "...[truncated]"


@contextmanager
def span(name: str, kind: str = "chain", inputs: Any = None, **attrs: Any) -> Iterator[Any]:
    """Start a span with LangSmith run type and optional inputs; record errors."""
    with trace.get_tracer("research-assistant").start_as_current_span(name) as s:
        s.set_attribute("langsmith.span.kind", kind)
        if inputs is not None:
            s.set_attribute("input.value", to_attr(inputs))
        for k, v in attrs.items():
            if v is not None:
                s.set_attribute(k, v if isinstance(v, (str, bool, int, float)) else to_attr(v))
        try:
            yield s
        except Exception as exc:
            s.record_exception(exc)
            s.set_status(Status(StatusCode.ERROR, str(exc)))
            raise


def current_trace_run_id() -> str | None:
    """LangSmith run id of the root of the current trace (what feedback should attach to)."""
    ctx = trace.get_current_span().get_span_context()
    if not ctx.is_valid:
        return None
    root = _ids.root_run_id(ctx.trace_id)
    return str(root) if root else None
