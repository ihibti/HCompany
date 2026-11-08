#!/usr/bin/env bash
# Demo rehearsal smoke test: boots the app on a spare port with a temp run
# store (+ committed demo_runs), checks pages, and runs a replay batch to
# batch_done over SSE. Exit non-zero on any failure.
set -euo pipefail
cd "$(dirname "$0")/.."
export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-$HOME/.venvs/hcompany}"

PORT="${REHEARSAL_PORT:-8799}"
BASE="http://127.0.0.1:${PORT}"
TMP="$(mktemp -d /tmp/eh-rehearsal.XXXXXX)"
SRV=""
cleanup() { [ -n "$SRV" ] && kill "$SRV" 2>/dev/null || true; rm -rf "$TMP"; }
trap cleanup EXIT

uv run escapehatch serve --port "$PORT" --host 127.0.0.1 \
  --store "$TMP/runs" --demo-store demo_runs >"$TMP/server.log" 2>&1 &
SRV=$!

ok=0
for _ in $(seq 1 80); do
  if curl -sf "$BASE/" -o /dev/null 2>&1; then ok=1; break; fi
  sleep 0.5
done
[ "$ok" = "1" ] || { echo "FAIL: server did not start"; cat "$TMP/server.log"; exit 1; }

fail=0
check() {
  local code
  code=$(curl -s -o /dev/null -w "%{http_code}" "$1")
  if [ "$code" = "200" ]; then echo "ok   $1"; else echo "FAIL $1 -> HTTP $code"; fail=1; fi
}

check "$BASE/"
check "$BASE/hall"
check "$BASE/benchmark"

AID="$(find demo_runs -mindepth 1 -maxdepth 1 -type d \
  ! -name benchmarks ! -name shots | head -1 | xargs -n1 basename)"
[ -n "$AID" ] || { echo "FAIL: no demo audit found"; exit 1; }
check "$BASE/audits/$AID"

BID="$(curl -s -X POST "$BASE/api/batches" -H 'Content-Type: application/json' \
  -d "{\"replay\":[\"$AID\"],\"speed\":20}" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["batch_id"])')"
echo "replay batch: $BID (audit $AID)"

if curl -sN --max-time 90 "$BASE/api/batches/$BID/events" | grep -m1 '"type": *"batch_done"' >/dev/null; then
  echo "ok   SSE batch_done received"
else
  echo "FAIL: no batch_done within 90s"; fail=1
fi

[ "$fail" = "0" ] && echo "REHEARSAL OK" || exit 1
