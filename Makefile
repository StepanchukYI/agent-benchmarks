.DEFAULT_GOAL := help
SHELL := /bin/bash

PY_PACKAGES := ab-datasets ab-harness ab-server ab-sdk ab-cli
JS_PACKAGE  := ab-leaderboard

.PHONY: help install install-py install-js dev-up dev-down test test-py test-js lint lint-py lint-js typecheck typecheck-py typecheck-js schema-export privacy-scan clean demo-mock demo-claude-code

help:
	@echo "Targets:"
	@echo "  install            uv sync (Python) + pnpm install (TS)"
	@echo "  dev-up             docker compose up (Postgres + ab-server + ab-leaderboard)"
	@echo "  dev-down           docker compose down"
	@echo "  demo-mock          run L0_smoke with MockRunner (no API key)"
	@echo "  demo-claude-code   run L0_smoke with ClaudeCodeRunner (needs ANTHROPIC_API_KEY + claude CLI)"
	@echo "  test               run all tests"
	@echo "  lint               ruff + eslint + prettier"
	@echo "  typecheck          mypy + tsc"
	@echo "  schema-export      regenerate docs/schemas/ from Pydantic"
	@echo "  privacy-scan       run privacy patterns scanner"
	@echo "  clean              remove build artifacts"

install: install-py install-js

install-py:
	uv sync --all-packages

install-js:
	cd packages/$(JS_PACKAGE) && pnpm install

dev-up:
	docker compose -f infra/docker-compose.yml up --build -d
	@echo ""
	@echo "Stack up:"
	@echo "  ab-server      http://localhost:8000  (healthz, /openapi.json)"
	@echo "  ab-leaderboard http://localhost:5173"

dev-down:
	docker compose -f infra/docker-compose.yml down

test: test-py test-js

test-py:
	uv run pytest -q

test-js:
	cd packages/$(JS_PACKAGE) && pnpm test --run

lint: lint-py lint-js

lint-py:
	uv run ruff check .

lint-js:
	cd packages/$(JS_PACKAGE) && pnpm lint

typecheck: typecheck-py typecheck-js

typecheck-py:
	uv run mypy packages

typecheck-js:
	cd packages/$(JS_PACKAGE) && pnpm typecheck

schema-export:
	uv run python -m ab_datasets.schemas.export --out docs/schemas

privacy-scan:
	uv run python scripts/privacy_scan.py

demo-mock:
	uv run ab run --suite L0_smoke --runner mock --tier T0 --results-root ./results

demo-claude-code:
	@if [ -z "$$ANTHROPIC_API_KEY" ]; then echo "ANTHROPIC_API_KEY not set"; exit 1; fi
	uv run ab run --suite L0_smoke --runner claude-code --model claude-sonnet-4-5 --tier T0 --results-root ./results

clean:
	rm -rf .venv .uv .ruff_cache .mypy_cache .pytest_cache
	rm -rf packages/$(JS_PACKAGE)/node_modules packages/$(JS_PACKAGE)/dist
	find packages -name __pycache__ -type d -prune -exec rm -rf {} +
