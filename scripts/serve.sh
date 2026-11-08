#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-$HOME/.venvs/hcompany}"
uv sync --quiet
exec uv run escapehatch serve --port 8765 --store runs --demo-store demo_runs "$@"
