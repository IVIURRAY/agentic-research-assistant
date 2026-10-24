# Local dev + validation. `make help` lists targets.
# Values from .env (if present) are exported to every command.
-include .env
export

BACKEND := cd backend &&
PY := .venv/bin/python

.PHONY: help setup db ingest test eval-retrieval eval eval-local api web up down smoke validate gif

help:
	@grep -hE '^[a-z-]+:.*## ' Makefile | awk -F':.*## ' '{printf "  %-16s %s\n", $$1, $$2}'

setup: ## Install backend (uv) and frontend (npm) dependencies
	$(BACKEND) uv sync
	cd frontend && npm ci

db: ## Start Postgres + pgvector in Docker
	docker compose up -d --wait postgres

ingest: db ## Chunk, embed and load data/notes into Postgres (idempotent)
	$(BACKEND) $(PY) -m app.ingest --notes-dir ../data/notes

test: ingest ## Unit + integration tests (LLM is scripted; no API key needed)
	$(BACKEND) $(PY) -m pytest -q

eval-retrieval: ingest ## Deterministic retrieval eval: recall@5 / MRR gate (no API key)
	$(BACKEND) $(PY) -m evals.retrieval_eval

eval: ingest ## Full agent eval (needs an LLM key; uploads to LangSmith if keyed)
	$(BACKEND) $(PY) -m evals.run_evals

eval-local: ingest ## Agent eval on 5 questions without LangSmith (quick, cheap check)
	$(BACKEND) $(PY) -m evals.run_evals --local --limit 5

api: ingest ## Run the API with reload on :8000
	$(BACKEND) .venv/bin/uvicorn app.main:app --reload --port 8000

web: ## Run the Next.js UI on :3000 (expects the API on :8000)
	cd frontend && npm run dev

up: ## Whole stack in Docker: postgres, ingest, api, web
	docker compose up --build

down: ## Stop the Docker stack
	docker compose down

smoke: ## Ask the running API one question and check the stream completes
	./scripts/smoke.sh

validate: test eval-retrieval ## Everything that runs without an API key
	cd frontend && npx tsc --noEmit
	@echo "\nOffline checks passed. With OPENROUTER_API_KEY set: make api, then make smoke / make eval-local."

gif: ## Re-render docs/architecture.gif and docs/agent-loop.gif
	$(BACKEND) $(PY) scripts/render_architecture_gif.py
	$(BACKEND) $(PY) scripts/render_agent_gif.py
