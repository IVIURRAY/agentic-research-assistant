"""Runtime settings, read once from the environment."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    database_url: str = field(
        default_factory=lambda: os.getenv(
            "DATABASE_URL", "postgresql://research:research@localhost:5432/research"
        )
    )
    notes_dir: str = field(default_factory=lambda: os.getenv("NOTES_DIR", "../data/notes"))

    # LLM: any OpenRouter model with tool calling (agent) and structured outputs (judge).
    openrouter_api_key: str | None = field(
        default_factory=lambda: os.getenv("OPENROUTER_API_KEY") or None
    )
    openrouter_base_url: str = field(
        default_factory=lambda: os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    )
    openrouter_model: str = field(
        default_factory=lambda: os.getenv(
            "OPENROUTER_MODEL", "nvidia/nemotron-3-super-120b-a12b:free"
        )
    )
    openrouter_judge_model: str = field(
        default_factory=lambda: os.getenv(
            "OPENROUTER_JUDGE_MODEL", "nvidia/nemotron-3-super-120b-a12b:free"
        )
    )
    max_agent_steps: int = field(default_factory=lambda: int(os.getenv("MAX_AGENT_STEPS", "8")))

    # Retrieval
    embed_model: str = field(
        default_factory=lambda: os.getenv("EMBED_MODEL", "BAAI/bge-small-en-v1.5")
    )
    embed_dim: int = field(default_factory=lambda: int(os.getenv("EMBED_DIM", "384")))
    reranker: str = field(default_factory=lambda: os.getenv("RERANKER", "local"))  # local|cohere|none
    rerank_model: str = field(
        default_factory=lambda: os.getenv("RERANK_MODEL", "Xenova/ms-marco-MiniLM-L-6-v2")
    )
    cohere_rerank_model: str = field(
        default_factory=lambda: os.getenv("COHERE_RERANK_MODEL", "rerank-v3.5")
    )
    candidate_k: int = field(default_factory=lambda: int(os.getenv("CANDIDATE_K", "40")))
    rerank_k: int = field(default_factory=lambda: int(os.getenv("RERANK_K", "24")))
    top_k: int = field(default_factory=lambda: int(os.getenv("TOP_K", "8")))
    rrf_k: int = 60

    # Telemetry
    otel_enabled: bool = field(default_factory=lambda: _bool("OTEL_ENABLED", True))
    service_name: str = field(
        default_factory=lambda: os.getenv("OTEL_SERVICE_NAME", "research-assistant-api")
    )
    langsmith_api_key: str | None = field(default_factory=lambda: os.getenv("LANGSMITH_API_KEY"))
    langsmith_project: str = field(
        default_factory=lambda: os.getenv("LANGSMITH_PROJECT", "research-assistant")
    )
    langsmith_endpoint: str = field(
        default_factory=lambda: os.getenv("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com")
    )


settings = Settings()
