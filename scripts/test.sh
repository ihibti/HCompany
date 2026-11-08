#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-$HOME/.venvs/hcompany}"
exec uv run pytest -q "$@"
