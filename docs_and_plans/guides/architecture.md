# Escape Hatch — architecture

## Modules (`src/escapehatch/`)

| module | role |
|--------|------|
| `models.py` | Pydantic domain types: `Task`, `Outcome`, `Step`, `Journey`, `Finding`, `Effort`, `Score`, `Audit`, `AgentAnswer` |
| `prompts.py` | Task definitions, enter-counterpart mapping, `build_task_prompt` |
| `events.py` | Pure event→journey conversion: `journey_from_events`, `step_from_policy_event`, `ACTION_KIND` table, outcome rules, wall-clock `duration_s` |
| `agent.py` | `run_journey` — H Agents API session, streaming, custom `request_confirmation` tool, `JourneyRun` control handle, `fetch_screenshot` |
| `keys.py` | `KeyPool` — weighted round-robin over `HAI_API_KEY` / `HCOMPANY_KEY` with per-org session limits |
| `patterns.py` | `select_key_steps`, `classify_step` (Models API `holo4-27b`, strict JSON schema, 120s timeout), `merge_findings`, `pattern_recall` |
| `scoring.py` | Pure friction scoring: `effort`, `effort_steps`, `score`, grade bands |
| `legal.py` | Maps findings → CNIL / French-law / DSA references |
| `report.py` + `templates/report.html` | Standalone dark-theme report renderer (inline CSS, relative `/shots/` paths) |
| `pipeline.py` | `run_audit` — orchestrates leave+enter journeys, screenshots, classification, scoring, persistence, `on_update` messages |
| `store.py` | `RunStore` — audit.json / events_*.json roundtrip, JPEG downscale ≤900px, `local_shot` lookup |
| `cli.py` | `audit`, `gauntlet`, `report`, `rescore`, `serve` |
| `server.py` | FastAPI app: pages, batches, SSE, confirmations, controls, shot proxy, replay |
| `gauntlet/` | Netflux benchmark site (published to GitHub Pages via gh-pages subtree) |

## Message protocol

`pipeline.run_audit(on_update=...)` emits normalized dicts; `server.py` tags them with `run`/`audit_id` and forwards over SSE. Live batches and replays emit identical types.

| type | fields | meaning |
|------|--------|---------|
| `start` | `run`, `site_url`, `task`, `agent`, `kind` | audit launched (live only) |
| `status` | `run`, `journey` (`leave`/`enter`/`audit`), `status` | journey/phase state |
| `step` | `run`, `journey`, `step`, `effort_so_far` | new step (observation + action) |
| `confirm_request` | `run`, `journey`, `id`, `action`, `replay_auto?` | agent asks approval; replay sets `replay_auto: true` |
| `finding` | `run`, `finding` | classified dark pattern |
| `done` | `run`, `audit_id`, `grade`, `friction`, `headline`, `outcome` | audit complete |
| `error` | `audit_id`, `message` | non-fatal failure |
| `batch_done` | `batch_id` | all audits in batch finished |

`GET /api/batches/{id}/events` replays buffered history on reconnect (history is source of truth; the queue is only a wakeup). `POST /api/audits/{run}/confirm/{id}` `{approved}` resolves the pending future (120s auto-deny); `POST .../pause|resume|stop`, `.../message` drive `JourneyRun`.

## Data layout

```
runs/                        # gitignored live data
  <audit_id>/
    audit.json               # full Audit (journeys, findings, score, legal)
    events_leave.json        # raw event envelopes (replay source)
    events_enter.json
    report.html              # rendered with /shots/ relative paths
  benchmarks/<ts>-<agent>.json
  shots/<sha>.jpg            # shared downscaled screenshot store
demo_runs/                   # committed curated runs, same layout + benchmark JSON
artifacts/screens/           # gitignored UI screenshots
```

## Scoring (exact formulas — `scoring.py`)

Effort: per step, `ACTION_KIND` buckets → `interactions`, `navigations` (first `go_to_web` is free), `detours`; `total = i + n + d`. Scroll/wait/request_confirmation cost nothing.

- `FAILED` → friction 0, grade `?` (inconclusive). `NOT_APPLICABLE` → `N/A`. `IMPOSSIBLE` → friction 100, grade F.
- `base = min(60, 6 * max(0, leave.total - 1))`
- If enter succeeded: `asymmetry_ratio = leave/enter`; `asym = min(20, 5 * max(0, leave.total - enter.total - 1))` (one extra step is legitimate — France's 3-click law).
- `pattern_points = min(30, sum(4 * max_severity(pattern)))`
- `friction = clamp(0..100, base + asym + pattern_points)`
- Grades: ≤10 A, ≤25 B, ≤45 C, ≤70 D, else F.

`pattern_recall` edge cases: empty predictions & empty truth → (1.0, 1.0); empty predictions, non-empty truth → precision 1.0, recall 0; non-empty predictions, empty truth → recall 1.0.

## Key pool (`keys.py`)

`KeyPool` holds `(api_key, session_limit)` slots from `HAI_API_KEY`/`HCOMPANY_KEY` env (separate orgs, limit 3 each → 6 concurrent sessions). `acquire()` picks the least-utilized slot under its limit and yields an `AsyncClient`; leave and enter journeys run in parallel. Models API classification can use either key.

## Security notes

- `/api/shot?u=` proxies only `https://` URLs on `agp.eu.hcompany.ai` / `agp.hcompany.ai` before attaching the bearer token.
- `/shots/{audit_id}/{name}` validates both params (`^[A-Za-z0-9._-]+$`, no `..`), resolves the path, and requires it to stay under the store root.
