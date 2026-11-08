# AGENTS.md — working notes for agents on this repo

## Build / test / serve

```bash
uv sync                                  # install deps
bash scripts/test.sh                     # full suite (pins UV_PROJECT_ENVIRONMENT)
bash scripts/serve.sh                    # dev server on :8765 (store runs + demo_runs)
uv run escapehatch serve --port 8765 --store runs --demo-store demo_runs
uv run escapehatch audit URL --task refuse_cookies --agent h/web-surfer-pro
uv run escapehatch gauntlet --levels 1-5 --agent h/web-surfer-pro
uv run escapehatch report <audit_id> --store runs
uv run escapehatch rescore --store runs
```

## Environment gotchas

- **`.venv` UF_HIDDEN**: this repo lives under `~/Documents` (iCloud-synced). macOS file-provider sync can set the `UF_HIDDEN` flag on `.venv`, which makes Python's `site.addpackage` silently skip `.pth` files → `ModuleNotFoundError: escapehatch` even though the dist-info exists. `scripts/serve.sh` and `scripts/test.sh` already export `UV_PROJECT_ENVIRONMENT=$HOME/.venvs/hcompany` (env outside Documents) — prefer them over bare `uv run`. Manual fix: `chflags -R nohidden .venv`, or `UV_PROJECT_ENVIRONMENT=$HOME/.venvs/hcompany uv run ...`. If imports break again, check `ls -lO .venv` for `hidden`.
- **Platform stalls**: H Agents sessions occasionally stall after `AgentStarted`/first observation and sit silent until `max_time` (~8 min) — observed ~15–30% of sessions on heavy sites and during degraded windows. `run_journey` records these as `session_status=failed`, grade `?`, and the audit is inconclusive (excluded from Hall). Retry inconclusive audits once before trusting a verdict. Demo mode (`demo_runs/` replays) is the venue-wifi fallback.
- **Access blocks**: agents set `access_blocked` when the site refuses to load (Akamai/Cloudflare/captcha/403) → `Outcome.BLOCKED` → grade `?`, headline "Inconclusive: the site blocked our agent." `escapehatch rescore --reclassify-blocked` retro-flags stored audits whose answer text matches block keywords.
- **Screenshot 404s**: some `agp.*` screenshot resource URLs return 404 (expired bucket objects). `pipeline` logs and skips them; reports degrade to "no screenshot" for those steps. Not fatal.

## Gauntlet republish

`gauntlet/` is published to GitHub Pages via a **subtree split to the `gh-pages` branch** → https://ihibti.github.io/HCompany/. The lead handles the push/publish — do NOT push `gh-pages` yourself; just report which gauntlet files changed.

## Data layout

- `runs/` (gitignored): live audits — `<audit_id>/audit.json`, `events_leave.json`, `events_enter.json`, `report.html`; `runs/benchmarks/*.json`; `runs/shots/` shared screenshot store.
- `demo_runs/` (committed, <40MB): curated audits for offline replay — same per-audit layout + a benchmark JSON. Every leave-step screenshot must be present for replay.
- `artifacts/screens/` (gitignored): UI screenshots for review.
- `.env`: `HAI_API_KEY`, optional `HCOMPANY_KEY` (second org → KeyPool capacity 6), `GLADIA_API_KEY` unused by this app.

## Conventions

- Pure logic in `events.py`/`scoring.py`/`patterns.py`/`legal.py` stays free of I/O; `agent.py`/`pipeline.py`/`server.py` do the API work.
- `on_update` message protocol (pipeline → SSE): `step`, `status`, `confirm_request`, `finding`, `done`, `error`, `batch_done`. Live and replay emit the same types; replay adds `replay_auto: true` on `confirm_request`.
- Commit messages: no AI attribution, no co-author lines.
- Interactive shell is nushell — any command handed to the user must be valid nu (use `;`, `$env.NAME`; wrap bash in `bash -c '...'`).
