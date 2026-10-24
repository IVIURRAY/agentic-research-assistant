"""Fast unit tests: no database, no network."""

import datetime as dt
from pathlib import Path

import pytest

from app.agent import cited_note_ids, route_after_agent
from app.ingest import chunk_note, embedding_text, parse_note
from app.retrieval import ChunkHit, SearchFilters, rrf_fuse
from app.telemetry import run_id_for
from app.tools import SearchNotesInput
from evals.metrics import gate, mrr, recall_at_k, trajectory_score

NOTES = Path(__file__).resolve().parents[2] / "data" / "notes"


def _hit(cid: str) -> ChunkHit:
    return ChunkHit(chunk_id=cid, note_id=cid.split("#")[0], title="t", ticker=None, company=None,
                    sector=None, rating=None, price_target=None, currency=None, analyst=None,
                    published_date="2026-01-01", heading=None, content="c")


def test_parse_and_chunk_by_paragraph():
    note = parse_note(NOTES / "asml-2026-04-16.md")
    assert note.ticker == "ASML" and note.rating == "Buy" and note.previous_rating == "Hold"
    assert note.published_date == dt.date(2026, 4, 16)
    chunks = chunk_note(note)
    # One chunk per paragraph; a section with two paragraphs yields two chunks.
    assert [c.heading for c in chunks] == [
        "Summary", "What changed", "Valuation", "Order book quality", "Order book quality",
        "Estimate changes", "Estimate changes", "Risks"]
    assert [c.chunk_id for c in chunks] == [f"asml-2026-04-16#{i}" for i in range(len(chunks))]
    # The one-line disclaimer is merged into the preceding Risks paragraph, not its own chunk.
    assert chunks[-1].content.startswith("Order lumpiness") and "Synthetic note" in chunks[-1].content
    header = embedding_text(note, chunks[0]).splitlines()[0]
    assert "ASML Holding (ASML)" in header and "2026-04-16" in header


def test_corpus_size():
    assert len(list(NOTES.glob("*.md"))) == 50


def test_rrf_rewards_agreement():
    fused = rrf_fuse({"dense": [_hit("a#0"), _hit("b#0")], "sparse": [_hit("b#0"), _hit("c#0")]})
    assert fused[0].chunk_id == "b#0"
    assert fused[0].ranks == {"dense": 2, "sparse": 1}


def test_filters_sql():
    where, params = SearchFilters(ticker="asml", date_from=dt.date(2026, 4, 1)).sql()
    assert "n.ticker = %s" in where and "n.published_date >= %s" in where
    assert params == ["ASML", dt.date(2026, 4, 1)]
    assert SearchFilters().sql() == ("TRUE", [])


def test_search_input_validation():
    args = SearchNotesInput.model_validate({"query": "q", "ticker": " ", "date_to": "2026-06-30"})
    assert args.ticker is None and args.date_to == dt.date(2026, 6, 30)
    with pytest.raises(Exception):
        SearchNotesInput.model_validate({"query": "q", "bogus": 1})
    with pytest.raises(Exception):
        SearchNotesInput.model_validate({"query": "q", "date_from": "last spring"})


def test_cited_note_ids():
    answer = "Upgraded [asml-2026-04-16]. Later raised [asml-2026-07-16, asml-2026-09-24] [x]."
    assert cited_note_ids(answer) == ["asml-2026-04-16", "asml-2026-07-16", "asml-2026-09-24"]


def test_routing():
    call = [{"id": "c1", "name": "search_notes", "input": {}, "parse_error": None}]
    assert route_after_agent({"pending_tool_calls": call, "steps": 1}) == "tools"
    assert route_after_agent({"pending_tool_calls": [], "steps": 1}) == "__end__"
    assert route_after_agent({"pending_tool_calls": call, "steps": 99}) == "__end__"


def test_retrieval_metrics():
    assert recall_at_k(["a", "b", "c"], ["c", "d"], k=3) == 0.5
    assert recall_at_k(["a", "b", "c"], ["c"], k=2) == 0.0
    assert mrr(["a", "b", "c"], ["c"]) == pytest.approx(1 / 3)
    assert mrr(["a"], ["z"]) == 0.0


def test_trajectory_score():
    calls = [{"name": "search_notes", "input": {"query": "x", "ticker": "asml"}}]
    assert trajectory_score(calls, ["search_notes"], {"ticker": ["ASML"]}) == (1.0, "all met")
    score, comment = trajectory_score(calls, ["search_notes"], {"ticker": ["ASML", "TSM"]})
    assert score == pytest.approx(2 / 3) and "ticker=TSM" in comment


def test_gate():
    assert gate({"a": 0.9}, {"a": 0.8}) == []
    assert gate({"a": 0.7}, {"a": 0.8, "b": 0.1}) == ["a: 0.700 < 0.800", "b: missing"]


def test_run_ids_are_deterministic_uuids():
    a = run_id_for(0x1234_5678_9ABC_DEF0_1111_2222_3333_4444, 0xAAAA_BBBB_CCCC_DDDD)
    assert a == run_id_for(0x1234_5678_9ABC_DEF0_1111_2222_3333_4444, 0xAAAA_BBBB_CCCC_DDDD)
    assert str(a) == "12345678-9abc-def0-aaaa-bbbbccccdddd"


def test_langsmith_id_processor_builds_consistent_tree():
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    from app.telemetry import LangSmithIdProcessor

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(LangSmithIdProcessor())
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("t")
    with tracer.start_as_current_span("root"):
        with tracer.start_as_current_span("child"):
            with tracer.start_as_current_span("grandchild"):
                pass

    spans = {s.name: s.attributes for s in exporter.get_finished_spans()}
    root, child, grand = spans["root"], spans["child"], spans["grandchild"]
    assert root["langsmith.trace.id"] == root["langsmith.span.id"]
    assert child["langsmith.trace.id"] == grand["langsmith.trace.id"] == root["langsmith.span.id"]
    assert child["langsmith.span.parent_id"] == root["langsmith.span.id"]
    assert grand["langsmith.span.parent_id"] == child["langsmith.span.id"]
    assert "langsmith.span.parent_id" not in root
    assert grand["langsmith.span.dotted_order"].startswith(child["langsmith.span.dotted_order"] + ".")
    assert child["langsmith.span.dotted_order"].startswith(root["langsmith.span.dotted_order"] + ".")
    assert root["langsmith.span.dotted_order"].endswith(root["langsmith.span.id"])


def test_openrouter_schema_and_json_helpers():
    from app.llm import _extract_json, _strict_schema
    from evals.judges import GroundednessVerdict

    schema = _strict_schema(GroundednessVerdict.model_json_schema())
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {"unsupported_claims", "grounded"}
    assert _extract_json('Sure!\n```json\n{"grounded": true}\n```') == '{"grounded": true}'
    assert _extract_json('verdict: {"a": {"b": 1}} done') == '{"a": {"b": 1}}'


def test_cited_note_ids_accepts_model_variants():
    answer = ("Hold 【asml-2026-01-14#0】. Buy 【asml-2026-04-16#0】 and [asml-2026-07-16; "
              "asml-2026-09-24#2]. Not a cite: [1] or [see below].")
    assert cited_note_ids(answer) == [
        "asml-2026-01-14", "asml-2026-04-16", "asml-2026-07-16", "asml-2026-09-24"]


async def test_evaluator_error_scores_zero_instead_of_crashing():
    from evals.run_evals import _apply

    async def groundedness(inputs, outputs, reference):
        raise RuntimeError("judge returned invalid JSON twice")

    result = await _apply(groundedness, {}, {}, {})
    assert result["key"] == "groundedness" and result["score"] == 0.0
    assert "invalid JSON" in result["comment"]
