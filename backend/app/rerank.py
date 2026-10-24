"""Second-stage reranking: local cross-encoder by default, Cohere Rerank if configured."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Protocol

from app.config import settings


class Reranker(Protocol):
    def scores(self, query: str, documents: list[str]) -> list[float]: ...


class LocalCrossEncoder:
    def __init__(self, model_name: str):
        from fastembed.rerank.cross_encoder import TextCrossEncoder

        self._encoder = TextCrossEncoder(model_name=model_name)

    def scores(self, query: str, documents: list[str]) -> list[float]:
        return [float(s) for s in self._encoder.rerank(query, documents)]


class CohereReranker:
    def __init__(self, model_name: str):
        import cohere

        self._client = cohere.ClientV2(api_key=os.environ["COHERE_API_KEY"])
        self._model = model_name

    def scores(self, query: str, documents: list[str]) -> list[float]:
        resp = self._client.rerank(model=self._model, query=query, documents=documents)
        out = [0.0] * len(documents)
        for r in resp.results:
            out[r.index] = float(r.relevance_score)
        return out


@lru_cache(maxsize=1)
def get_reranker() -> Reranker | None:
    kind = settings.reranker.lower()
    if kind == "none":
        return None
    if kind == "cohere":
        return CohereReranker(settings.cohere_rerank_model)
    return LocalCrossEncoder(settings.rerank_model)
