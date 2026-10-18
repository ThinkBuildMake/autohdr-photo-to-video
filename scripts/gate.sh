#!/usr/bin/env bash
# Regression gate: lint, format check and the whole test suite (Playwright included).
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
export FAKE_PROVIDERS=1
uv sync --locked
uv run ruff check .
uv run ruff format --check .
uv run pytest
