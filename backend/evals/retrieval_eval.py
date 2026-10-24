"""Retrieval eval: recall@k and MRR of hybrid search against gold note ids.

Deterministic and cheap (local models + Postgres, no LLM calls), so it runs on every CI build and
catches most retrieval regressions before the slower agent eval.

    python -m evals.retrieval_eval [--k 5] [--no-rerank] [--json out.json]
"""

from __future__ import annotations

import argparse
import json
import sys

from app.retrieval import hybrid_search
from evals.metrics import dedupe, gate, load_dataset, load_thresholds, mean, mrr, recall_at_k


def run(k: int, rerank: bool) -> dict:
    rows = []
    for ex in load_dataset():
        hits = hybrid_search(ex["question"], top_k=20, rerank=rerank)
        ranked = dedupe(h.note_id for h in hits)
        rows.append({
            "id": ex["id"],
            "question": ex["question"],
            "gold": ex["gold_note_ids"],
            "ranked": ranked[:k],
            f"recall@{k}": recall_at_k(ranked, ex["gold_note_ids"], k),
            "mrr": mrr(ranked, ex["gold_note_ids"]),
        })
    summary = {
        f"recall@{k}": mean([r[f"recall@{k}"] for r in rows]),
        "mrr": mean([r["mrr"] for r in rows]),
    }
    return {"summary": summary, "rows": rows}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--no-rerank", action="store_true")
    parser.add_argument("--json", help="write full report here")
    parser.add_argument("--no-gate", action="store_true")
    args = parser.parse_args()

    report = run(args.k, rerank=not args.no_rerank)
    for r in report["rows"]:
        flag = "  " if r[f"recall@{args.k}"] == 1 else "!!"
        print(f"{flag} {r['id']} recall={r[f'recall@{args.k}']:.2f} mrr={r['mrr']:.2f}  "
              f"{r['question'][:60]}")
        if flag == "!!":
            print(f"     gold={r['gold']}\n     got ={r['ranked']}")
    print("\nsummary:", json.dumps(report["summary"], indent=2))
    if args.json:
        with open(args.json, "w") as f:
            json.dump(report, f, indent=2)

    if not args.no_gate:
        thresholds = load_thresholds()["retrieval"]
        failures = gate(report["summary"], thresholds)
        if failures:
            print("RETRIEVAL GATE FAILED:\n  " + "\n  ".join(failures))
            sys.exit(1)
        print("retrieval gate passed")


if __name__ == "__main__":
    main()
