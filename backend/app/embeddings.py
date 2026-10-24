"""Local embeddings (fastembed / ONNX) so the stack needs only one API key."""

from __future__ import annotations

from functools import lru_cache

import numpy as np
from fastembed import TextEmbedding

from app.config import settings


@lru_cache(maxsize=1)
def _model() -> TextEmbedding:
    return TextEmbedding(model_name=settings.embed_model)


def embed_passages(texts: list[str]) -> list[np.ndarray]:
    return list(_model().embed(texts))


def embed_query(text: str) -> np.ndarray:
    return next(iter(_model().query_embed([text])))
