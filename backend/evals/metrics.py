"""Deterministic eval metrics (no LLM): retrieval and trajectory."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

DATASET_PATH = Path(__file__).with_name("dataset.jsonl")
THRESHOLDS_PATH = Path(__file__).with_name("thresholds.json")


def load_dataset(path: Path = DATASET_PATH) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def load_thresholds() -> dict[str, dict[str, float]]:
    return json.loads(THRESHOLDS_PATH.read_text())


def dedupe(ids: Iterable[str]) -> list[str]:
    out: list[str] = []
    for i in ids:
        if i not in out:
            out.append(i)
    return out


def recall_at_k(ranked: list[str], gold: list[str], k: int | None = None) -> float:
    if not gold:
        return 1.0
    top = set(ranked[:k] if k else ranked)
    return len(top & set(gold)) / len(set(gold))


def mrr(ranked: list[str], gold: list[str]) -> float:
    gold_set = set(gold)
    for i, note_id in enumerate(ranked, start=1):
        if note_id in gold_set:
            return 1.0 / i
    return 0.0


def trajectory_score(calls: list[dict[str, Any]], expected_tools: list[str],
                     expected_filters: dict[str, list[str]]) -> tuple[float, str]:
    """Fraction of expectations met: each expected tool was called, and each expected filter
    value (e.g. ticker=ASML) appears in at least one search_notes call."""
    checks: list[tuple[str, bool]] = []
    called = {c["name"] for c in calls}
    for tool in expected_tools:
        checks.append((f"called {tool}", tool in called))
    searches = [c.get("input") or {} for c in calls if c["name"] == "search_notes"]
    for key, values in expected_filters.items():
        for value in values:
            hit = any(str(s.get(key) or "").lower() == str(value).lower() for s in searches)
            checks.append((f"{key}={value}", hit))
    if not checks:
        return 1.0, "no expectations"
    passed = sum(ok for _, ok in checks)
    missed = [name for name, ok in checks if not ok]
    return passed / len(checks), ("missed: " + ", ".join(missed)) if missed else "all met"


def mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def gate(scores: dict[str, float], thresholds: dict[str, float]) -> list[str]:
    """Return a list of failures (empty means pass)."""
    failures = []
    for key, minimum in thresholds.items():
        value = scores.get(key)
        if value is None:
            failures.append(f"{key}: missing")
        elif value < minimum:
            failures.append(f"{key}: {value:.3f} < {minimum:.3f}")
    return failures
