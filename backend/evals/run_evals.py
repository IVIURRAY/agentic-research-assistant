"""Agent eval: runs the full agent on the graded questions and scores four things.

    retrieval   recall / MRR of the notes the agent actually retrieved (and cited)
    answer      correctness vs reference, groundedness vs cited chunks (LLM-as-judge)
    trajectory  right tools called, right filters extracted

With LANGSMITH_API_KEY set, results are uploaded as a LangSmith experiment against a dataset
synced from evals/dataset.jsonl. Without it (or with --local) the same evaluators run locally.
Either way the run exits non-zero if any aggregate score is below evals/thresholds.json, which
is what makes it a CI release gate.

    python -m evals.run_evals [--local] [--limit N] [--concurrency 4]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections import defaultdict
from typing import Any

from app.agent import cited_note_ids, run_agent
from app.config import settings
from evals.judges import judge_correctness, judge_groundedness
from evals.metrics import (
    dedupe,
    gate,
    load_dataset,
    load_thresholds,
    mean,
    mrr,
    recall_at_k,
    trajectory_score,
)

DATASET_NAME = os.getenv("EVAL_DATASET", "research-assistant-golden")


# --------------------------------------------------------------------------- target

async def target(inputs: dict[str, Any]) -> dict[str, Any]:
    state = await run_agent(inputs["question"])
    answer = state.get("answer", "")
    sources = state.get("sources", {})
    evidence = {
        nid: "\n\n".join(
            f"[{c.get('heading') or ''}] {c['content']}" for c in src.get("chunks", [])
        )
        for nid, src in sources.items()
    }
    return {
        "answer": answer,
        "cited": cited_note_ids(answer),
        "retrieved": list(sources.keys()),  # first-seen order across tool calls
        "trajectory": state.get("trajectory", []),
        "evidence": evidence,
    }


# --------------------------------------------------------------------------- evaluators
# Signature (inputs, outputs, reference_outputs) works for both LangSmith and the local runner.

def retrieval_recall(inputs, outputs, reference_outputs) -> dict:
    return {"key": "retrieval_recall",
            "score": recall_at_k(outputs["retrieved"], reference_outputs["gold_note_ids"])}


def retrieval_mrr(inputs, outputs, reference_outputs) -> dict:
    return {"key": "retrieval_mrr",
            "score": mrr(dedupe(outputs["retrieved"]), reference_outputs["gold_note_ids"])}


def citation_recall(inputs, outputs, reference_outputs) -> dict:
    return {"key": "citation_recall",
            "score": recall_at_k(outputs["cited"], reference_outputs["gold_note_ids"])}


def trajectory(inputs, outputs, reference_outputs) -> dict:
    score, comment = trajectory_score(
        outputs["trajectory"],
        reference_outputs["expected_tools"],
        reference_outputs["expected_filters"],
    )
    return {"key": "trajectory", "score": score, "comment": comment}


async def correctness(inputs, outputs, reference_outputs) -> dict:
    v = await judge_correctness(inputs["question"], outputs["answer"],
                                reference_outputs["reference_answer"])
    return {"key": "correctness", "score": float(v.correct), "comment": v.reasoning}


async def groundedness(inputs, outputs, reference_outputs) -> dict:
    cited = set(outputs["cited"])
    evidence = {k: v for k, v in outputs["evidence"].items() if k in cited} or outputs["evidence"]
    v = await judge_groundedness(outputs["answer"], evidence)
    comment = "; ".join(v.unsupported_claims) or "all claims supported"
    return {"key": "groundedness", "score": float(v.grounded), "comment": comment}


EVALUATORS = [retrieval_recall, retrieval_mrr, citation_recall, trajectory, correctness,
              groundedness]


# --------------------------------------------------------------------------- runners

def _split(ex: dict[str, Any]) -> tuple[dict, dict]:
    inputs = {"question": ex["question"]}
    outputs = {k: ex[k] for k in
               ("gold_note_ids", "reference_answer", "expected_tools", "expected_filters")}
    return inputs, outputs


async def _apply(fn, inputs, outputs, reference) -> dict:
    """A judge that errors scores 0 for that example instead of aborting the whole run."""
    try:
        res = fn(inputs, outputs, reference)
        return await res if asyncio.iscoroutine(res) else res
    except Exception as exc:
        return {"key": fn.__name__, "score": 0.0,
                "comment": f"evaluator error: {type(exc).__name__}: {str(exc)[:200]}"}


async def run_local(examples: list[dict], concurrency: int) -> dict[str, list[float]]:
    sem = asyncio.Semaphore(concurrency)
    scores: dict[str, list[float]] = defaultdict(list)

    async def one(ex):
        inputs, reference = _split(ex)
        async with sem:
            outputs = await target(inputs)
            results = [await _apply(fn, inputs, outputs, reference) for fn in EVALUATORS]
        line = " ".join(f"{r['key']}={r['score']:.2f}" for r in results)
        print(f"{ex['id']}: {line}")
        for r in results:
            scores[r["key"]].append(r["score"])
            if r["score"] < 1 and r.get("comment"):
                print(f"    {r['key']}: {r['comment']}")

    await asyncio.gather(*(one(ex) for ex in examples))
    return scores


def sync_dataset(client, examples: list[dict]) -> str:
    """Create the LangSmith dataset if missing and add examples it doesn't have yet."""
    if client.has_dataset(dataset_name=DATASET_NAME):
        dataset = client.read_dataset(dataset_name=DATASET_NAME)
    else:
        dataset = client.create_dataset(
            DATASET_NAME, description="Graded questions for the research assistant")
    existing = {ex.metadata.get("qid") for ex in client.list_examples(dataset_id=dataset.id)
                if ex.metadata}
    new = [ex for ex in examples if ex["id"] not in existing]
    if new:
        client.create_examples(
            dataset_id=dataset.id,
            examples=[{"inputs": _split(ex)[0], "outputs": _split(ex)[1],
                       "metadata": {"qid": ex["id"]}} for ex in new],
        )
    return DATASET_NAME


async def run_langsmith(examples: list[dict], concurrency: int,
                        label: str | None = None) -> dict[str, list[float]]:
    from langsmith import Client, aevaluate

    client = Client()
    name = sync_dataset(client, examples)
    ids = {ex["id"] for ex in examples}
    data = [ex for ex in client.list_examples(dataset_name=name)
            if ex.metadata and ex.metadata.get("qid") in ids]
    results = await aevaluate(
        target,
        data=data,
        evaluators=EVALUATORS,
        experiment_prefix="-".join(filter(None, [label, settings.openrouter_model.replace("/", "_")])),
        metadata={"label": label, "model": settings.openrouter_model,
                  "judge_model": settings.openrouter_judge_model,
                  "reranker": settings.reranker, "candidate_k": settings.candidate_k,
                  "rerank_k": settings.rerank_k, "git_sha": os.getenv("GITHUB_SHA", "local")},
        max_concurrency=concurrency,
    )
    scores: dict[str, list[float]] = defaultdict(list)
    async for row in results:
        for r in row["evaluation_results"]["results"]:
            if r.score is not None:
                scores[r.key].append(float(r.score))
    print(f"LangSmith experiment: {results.experiment_name}")
    return scores


CALLS_PER_QUESTION = 4  # ~2 agent turns + 2 judge calls (measured on Nemotron 3 Super)


def openrouter_quota_check(n_questions: int) -> None:
    """Free OpenRouter models share a 50-requests/day account quota. Check it before starting
    so an exhausted quota is a one-line message, not a run of 429 retries and an empty
    LangSmith experiment."""
    import datetime as dt
    import urllib.request

    if not settings.openrouter_model.endswith(":free"):
        return
    req = urllib.request.Request(
        f"{settings.openrouter_base_url.rstrip('/')}/key",
        headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            quota = json.load(resp)["data"].get("free_model_daily_requests") or {}
    except Exception as exc:  # don't block the run on a failed check
        print(f"(couldn't check OpenRouter quota: {exc})")
        return
    remaining, limit = quota.get("remaining"), quota.get("limit")
    if remaining is None:
        return
    needed = n_questions * CALLS_PER_QUESTION
    now = dt.datetime.now(dt.timezone.utc)
    reset = (now + dt.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    hours = (reset - now).total_seconds() / 3600
    print(f"OpenRouter free quota: {remaining}/{limit} requests left today; "
          f"this run needs about {needed}.", flush=True)
    if remaining >= needed:
        return
    fits = remaining // CALLS_PER_QUESTION
    options = [f"run with --limit {fits} to fit what's left"] if fits else []
    options.append(f"wait for the reset at 00:00 UTC (in {hours:.1f}h)")
    sys.exit(f"Not enough OpenRouter free quota for {n_questions} questions: "
             f"{', or '.join(options)}. Skip this check with --skip-quota-check.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--local", action="store_true", help="don't upload to LangSmith")
    parser.add_argument("--limit", type=int, help="only the first N questions")
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--json", help="write summary scores here")
    parser.add_argument("--skip-quota-check", action="store_true")
    parser.add_argument("--label", help="name prefix for the LangSmith experiment, e.g. before")
    args = parser.parse_args()

    examples = load_dataset()[: args.limit] if args.limit else load_dataset()
    if not args.skip_quota_check:
        openrouter_quota_check(len(examples))
    use_langsmith = bool(settings.langsmith_api_key) and not args.local
    if use_langsmith:
        scores = asyncio.run(run_langsmith(examples, args.concurrency, args.label))
    else:
        scores = asyncio.run(run_local(examples, args.concurrency))

    summary = {k: mean(v) for k, v in sorted(scores.items())}
    if not summary:
        sys.exit("\nNo questions completed, so there is nothing to score. See the errors above.")
    print("\nsummary:", json.dumps(summary, indent=2))
    if args.json:
        with open(args.json, "w") as f:
            json.dump({"summary": summary, "n": len(examples)}, f, indent=2)

    failures = gate(summary, load_thresholds()["agent"])
    if failures:
        print("AGENT EVAL GATE FAILED:\n  " + "\n  ".join(failures))
        sys.exit(1)
    print("agent eval gate passed")


if __name__ == "__main__":
    main()
