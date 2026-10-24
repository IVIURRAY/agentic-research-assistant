# Iterations

How this project changed after the first build, and the evidence behind each change. Every
iteration below was driven, checked or caught by an evaluation, which is the point of having
them: with an LLM in the loop, "it looks fine when I try it" is not evidence.

- [How we evaluate](#how-we-evaluate)
- [1. Baseline](#1-baseline-19-oct-2026)
- [2. Moving to a free model surfaced three hidden failures](#2-moving-to-a-free-model-surfaced-three-hidden-failures-19-oct-2026)
- [3. Simplifying the agent, with tests for the behaviour that matters](#3-simplifying-the-agent-with-tests-for-the-behaviour-that-matters-24-oct-2026)
- [4. Longer notes and paragraph chunks](#4-longer-notes-and-paragraph-chunks-24-oct-2026)
- [Lessons about evals themselves](#lessons-about-evals-themselves)
- [Reproducing these numbers](#reproducing-these-numbers)

---

## How we evaluate

Four levels, cheapest first. The cheap ones run on every build; the LLM-judged ones run when a
model key is available, and every run lands in LangSmith as an experiment.

| Level | Question it answers | How | Cost |
|---|---|---|---|
| **Retrieval** | Does search put the right notes near the top? | recall@5 and MRR against gold note ids, bare question, no filters | Free, deterministic, seconds |
| **Trajectory** | Did the agent call the right tools with the right filters? | Compare tool calls with the expected ones | Free once the agent has run |
| **Answer** | Is the answer right, and is every claim backed by a cited note? | Correctness and groundedness, judged by an LLM with structured output | ~2 judge calls per question |
| **Online** | Do users find answers useful? | Thumbs up/down in the UI, written to the trace in LangSmith | Live |

The dataset is 30 questions over 50 synthetic notes, each with gold note ids, a reference
answer, and expected tools and filters ([`backend/evals/dataset.jsonl`](../backend/evals/dataset.jsonl)).
Thresholds in [`thresholds.json`](../backend/evals/thresholds.json) turn the scores into a CI gate.

**What LangSmith adds.** The scores alone say *that* something changed; LangSmith shows *why*:

- **Experiments.** Each eval run is an experiment on the `research-assistant-golden` dataset.
  Selecting two and clicking **Compare** shows them side by side per question, with the regressions
  highlighted, so a 0.1 drop in an average turns into "these two questions, these two claims".
- **Traces behind every score.** Each row links to the full trace: every agent step, the exact
  prompt, each tool call with its filters, and the dense, sparse and rerank stages of each search.
  A low groundedness score can be followed straight to the sentence the judge flagged and the
  chunks the model actually saw.
- **Judge reasoning.** Every LLM-judged score carries the judge's explanation as a comment, which is
  how we found the judge was too strict in iteration 2.
- **Threads and feedback.** In production use, traces group by chat session, and thumbs feedback
  attaches to the exact trace that produced the answer.

<!-- A screenshot of the LangSmith compare view (iteration 4's two experiments) fits well here:
     docs/img/langsmith-compare.png -->

---

## 1. Baseline (19 Oct 2026)

First end-to-end build: LangGraph agent on Claude, Postgres + pgvector hybrid search with a
cross-encoder reranker, Next.js UI, OpenTelemetry tracing to LangSmith.

| Retrieval eval | recall@5 | MRR |
|---|---|---|
| Baseline | 0.914 | 0.838 |

---

## 2. Moving to a free model surfaced three hidden failures (19 Oct 2026)

**Change.** Claude API keys are billed separately from Claude subscriptions, so the agent moved to
OpenRouter with a free NVIDIA Nemotron model. The agent code stayed the same apart from the API
client.

**What the evals caught.** The first smoke test against Nemotron failed even though the answer was
correct, and the first 5-question agent eval failed its gate:

| Agent eval, 5 questions | citation recall | trajectory | correctness | groundedness |
|---|---|---|---|---|
| First Nemotron run | 0.90 | 0.80 | 0.40 | 0.60 |

Reading the per-question results and the judge's comments showed three separate problems, none of
which a quick manual try would have revealed:

1. **Citations weren't recognised.** Nemotron cites as `【asml-2026-01-14#0】` (full-width brackets
   and a chunk suffix copied from the tool output) instead of `[asml-2026-01-14]`. The answers
   looked fine, but no citations were parsed, so the UI's citation chips and the citation metrics
   were silently broken. Fix: accept both forms in the backend and UI, stop exposing chunk ids to
   the model, and tighten the citation instructions.
2. **The judge was too strict.** Its comments showed it failing answers for leaving out reference
   details the question never asked for (for example, giving TSMC's price target correctly but not
   restating the rating). Fix: grade against what the question asks; a wrong number still fails.
3. **Filters and summary citations were skipped.** Some searches omitted `ticker` or `sector`, and
   opening summary sentences had no citation. Fix: explicit prompt rules for both.

After the fixes, questions 2–5 scored 1.0 on correctness and trajectory. The free tier's daily
request limit stopped a full re-run that day, and the run also exposed a fourth issue: the
judge's structured output was cut off mid-JSON because the model's hidden reasoning used up the
token budget. That was fixed with a larger budget, one retry, and scoring a failed judge call as 0
instead of aborting the run.

**Why it matters.** Every one of these was a quality problem, not a crash. Without per-question
scores and the judge's written reasoning, the move to a cheaper model would have shipped with
broken citations.

---

## 3. Simplifying the agent, with tests for the behaviour that matters (24 Oct 2026)

**Change.** A code review after removing the Anthropic path found a provider abstraction with one
implementation and two behavioural bugs:

- **The "answer" included narration.** The final answer concatenated every turn's text, so a model
  that writes "Let me search the notes" before a tool call had that line in the answer the judges
  scored. Now the answer is the final reply only.
- **The step budget only asked politely.** When the tool-call budget ran out, a system note asked
  the model to answer; a model that ignored it ended with no answer at all. Now the final call runs
  with tools disabled (`tool_choice="none"`), so an answer is guaranteed.

**Evidence.** Both are covered by tests with a scripted model: one that narrates before calling a
tool (the narration must not be the answer), and one that never stops searching (the third call
must have tools disabled and still produce a cited answer). The provider class became two plain
functions; the graph routes on whether the reply contains tool calls.

---

## 4. Longer notes and paragraph chunks (24 Oct 2026)

**Problem.** The full-note viewer highlighted the whole note instead of the passage the agent
used. Measuring the chunks showed why: half the notes were a single paragraph of about 340
characters, so the whole note was one chunk. Changing the chunker alone would have changed almost
nothing.

**Change.**

- Every note gained two or three note-specific sections of a few paragraphs each (about 3.5 times
  more text). The original text is unchanged, so every fact the evals check is still there word
  for word, and the generator rejects new text containing digits, so no new number can compete
  with the facts the evals test.
- Chunks are now one paragraph within a section, with the heading embedded alongside. One-line
  paragraphs merge into the previous one.

**Retrieval eval, step by step.** Changing one thing at a time showed the longer notes, not the
chunker, caused the first drop, and pointed to the fix:

| | recall@5 | MRR |
|---|---|---|
| Baseline | 0.914 | 0.838 |
| + longer notes (section chunks) | 0.875 | 0.832 |
| + paragraph chunks | 0.864 | 0.834 |
| + `CANDIDATE_K` 40 → 80 | **0.906** | **0.841** |

With about four chunks per note, the 40 candidates fetched per search leg covered too few distinct
notes. Fetching 80 is cheap (it's SQL); the reranker still scores 24, so search latency didn't
change. Raising the rerank count instead gave the same scores at double the latency
(455 ms vs 246 ms).

**Agent eval in LangSmith.** Both versions ran the full 30 questions as experiments,
`before-short-notes` and `after-paragraph-chunks`, with the same agent, model
(`nvidia/nemotron-3.5-super-vl:free`) and judge. Compared on the 21 questions both runs answered
and scored:

| Metric | Before | After | Change |
|---|---|---|---|
| Retrieval recall | 0.976 | 1.000 | +0.024 |
| Retrieval MRR | 0.750 | 0.832 | **+0.082** |
| Citation recall | 0.937 | 0.960 | +0.024 |
| Trajectory | 1.000 | 1.000 | 0 |
| Correctness | 1.000 | 1.000 | 0 |
| Groundedness | 0.762 | 0.667 | −0.095 |

**Reading it.**

- **Retrieval improved where it counts.** With the agent's own filters, the right note ranks
  higher (MRR +0.08). The filter-free retrieval eval above, a deliberately harsh test, shows a
  slight recall dip, so both views are worth keeping.
- **Correctness and trajectory are saturated.** The judge's reasoning shows those scores are real,
  but these 30 questions are too easy to separate the versions on those measures. The dataset
  needs harder questions.
- **Groundedness dipped by two questions out of 21** (16 vs 14). That's within the noise of an LLM
  judge on a sample this size, but it's the metric to watch: longer notes give the model more
  qualitative text to paraphrase loosely. Both runs miss the 0.80 gate, and the LangSmith compare
  view lists the exact claims the judge flagged.

---

## Lessons about evals themselves

- **Errored examples silently disappear from averages.** In the iteration 4 runs, the free model's
  stream dropped on 3 questions in one run and 1 in the other. LangSmith leaves an unscored
  example out of the average rather than counting it as 0, so the raw averages compared different
  question sets. Compare runs on the questions both completed.
- **Read the judge's reasoning, not just its score.** The too-strict judge in iteration 2 was only
  visible in its comments. A perfect score deserves the same scrutiny: in iteration 4 a 1.0
  correctness looked suspicious, and the comments confirmed it was earned.
- **Change one thing at a time.** Splitting iteration 4 into steps turned "retrieval got worse"
  into a specific, cheap fix.
- **Cheap, deterministic evals catch most regressions.** The retrieval eval needs no model, runs
  in seconds on every build, and caught the chunking regression before any LLM was involved.

---

## Reproducing these numbers

```bash
make eval-retrieval                                   # retrieval eval, no API key needed
cd backend && .venv/bin/python -m evals.run_evals --label my-change   # full agent eval → LangSmith
```

With `LANGSMITH_API_KEY` set, the agent eval uploads an experiment named `my-change-<model>` to the
`research-assistant-golden` dataset, with the retrieval settings recorded in its metadata. Select
it alongside an earlier experiment and click **Compare**.

The LangSmith experiments referenced here live in the project owner's workspace. To make them
viewable by others, share them from LangSmith (it can create public links).
