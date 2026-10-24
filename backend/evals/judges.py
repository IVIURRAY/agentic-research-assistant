"""LLM-as-judge evaluators: answer correctness vs reference, and groundedness vs cited chunks."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app import llm


class CorrectnessVerdict(BaseModel):
    reasoning: str = Field(description="One or two sentences comparing answer to reference.")
    correct: bool = Field(description="True if the answer conveys the reference's key facts "
                                      "without contradicting it.")


class GroundednessVerdict(BaseModel):
    unsupported_claims: list[str] = Field(
        description="Factual claims in the answer not supported by the cited evidence.")
    grounded: bool = Field(description="True if every factual claim is supported by evidence "
                                       "from a note it cites.")


CORRECTNESS_PROMPT = """You are grading an equity research assistant.

Question: {question}

Reference answer: {reference}

Assistant answer: {answer}

Is the assistant answer correct? Judge it against what the question asks:
- It must state the facts from the reference that answer the question (e.g. the rating, price \
target, number, date or reason the question asks for).
- It must not contradict the reference anywhere; a wrong number, rating or date is incorrect.
- The reference may include extra context the question did not ask for; leaving that out is fine.
- Extra correct detail is fine."""

GROUNDEDNESS_PROMPT = """You are checking whether an answer is grounded in its cited sources.

Each claim in the answer should be followed by a citation like [note-id]. Below is the text of \
every note the assistant retrieved, keyed by note_id.

<evidence>
{evidence}
</evidence>

<answer>
{answer}
</answer>

List every factual claim that is not supported by the evidence of a note it cites (or that has \
no citation at all). Ignore framing sentences that make no factual claim. The answer is grounded \
only if that list is empty."""


async def _judge(prompt: str, schema: type[BaseModel]) -> BaseModel:
    # OPENROUTER_JUDGE_MODEL, with structured (JSON schema) output.
    return await llm.parse(prompt, schema)


async def judge_correctness(question: str, answer: str, reference: str) -> CorrectnessVerdict:
    return await _judge(
        CORRECTNESS_PROMPT.format(question=question, reference=reference, answer=answer or "(empty)"),
        CorrectnessVerdict,
    )


async def judge_groundedness(answer: str, evidence: dict[str, str]) -> GroundednessVerdict:
    ev = "\n\n".join(f"<note id=\"{nid}\">\n{text}\n</note>" for nid, text in evidence.items())
    return await _judge(
        GROUNDEDNESS_PROMPT.format(evidence=ev or "(no evidence retrieved)",
                                   answer=answer or "(empty)"),
        GroundednessVerdict,
    )
