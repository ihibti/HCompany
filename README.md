# Escape Hatch

A computer-use agent that tries to *leave* websites for you — refusing cookies, unsubscribing, cancelling subscriptions — and measures every dark pattern standing in the way. Every verdict comes with screenshot evidence and the law it touches.

![Escape Hatch race view](docs/assets/hero.png)

Netflux Level 5 — the agent fights the boss level's chatbot, pause-button and hidden escape link:

![Netflux L5 replay](docs/assets/netflux-l5.gif)

Three genuine cookie walls side by side (20minutes, Ouest-France, Le Figaro):

![French media race](docs/assets/french-media-race.gif)

## Quickstart

```bash
uv sync
# create .env with HAI_API_KEY (+ optional HCOMPANY_KEY for a second org quota)
bash scripts/serve.sh          # or: uv run escapehatch serve --port 8765
```

Open http://127.0.0.1:8765 — launch audits live, replay curated demos, browse the Hall of Shame and the Netflux benchmark. Demo mode replays stored runs with no API spend (venue-wifi fallback).

Requires Python 3.12+ and the H Agents/Models API keys.

## CLI

```bash
# Audit sites (refuse cookies vs accept) — runs journeys in parallel via KeyPool
uv run escapehatch audit https://www.lemonde.fr --task refuse_cookies --agent h/web-surfer-pro

# Run the Netflux gauntlet (cancel subscription, levels 1–5)
uv run escapehatch gauntlet --levels 1-5 --agent h/web-surfer-pro

# Re-render a stored report from audit.json + shots (no API)
uv run escapehatch report <audit_id> --store runs

# Recompute scores for all stored audits after scoring-rule changes (no API)
uv run escapehatch rescore --store runs
```

## Architecture

```
agent (H Agents API, cloud browser)
  │  streamed events (tool calls, observations, answers)
  ▼
events.py ──► journey (steps, effort, outcome, obstacles)
  │
  ▼
patterns.py ──► classify key screenshots (Models API, holo4-27b)
  │            → findings (11-pattern dark-pattern taxonomy)
  ▼
scoring.py ──► friction + grade (leave vs enter asymmetry, pattern cap)
  │
  ▼
legal.py ──► CNIL / French law / DSA references
  │
  ▼
report.py ──► standalone report.html + stored run (replayable)
```

`server.py` wraps the pipeline in a FastAPI app: live batches and event replays share one SSE message protocol (`step`, `status`, `confirm_request`, `finding`, `done`, `batch_done`), with in-memory history so reconnects replay from the start.

## Netflux gauntlet

https://ihibti.github.io/HCompany/ — five fictional streaming-service levels with escalating dark patterns and ground-truth pattern labels. `escapehatch gauntlet` runs cancel-subscription audits against it and writes `runs/benchmarks/*.json`; `/benchmark` compares agents.

## Results

### Hall of Shame (refuse-cookies audits, friction 100 = impossible)

| site | grade | verdict |
|------|-------|---------|
| 20minutes.fr | F | refused all 7 cookie categories → redirected to 1.99€/mo paywall |
| allocine.fr | F | pay 2€/mo or accept all |
| jeuxvideo.com | F | pay 2€/mo or accept all — no refuse path |
| lemonde.fr | F | free access requires consent |
| leparisien.fr | F | only "Accepter" or "S'abonner et refuser" |
| ouest-france.fr | F | refuse-all → paywall (2€/30d or 6.99€/mo) |

6 of the 19 conclusively audited sites (latest run per site) make refusing cookies impossible without paying. Verdicts can vary between runs: lefigaro.fr redirected "continue without accepting" to its subscription page in one run (F) but offered a refusal path in the latest one (C).

### Netflux benchmark (latest run per level; success counts across all runs, shortcuts excluded)

Runs that cheated — web search/fetch, direct URL jumps, off-site visits — are verified as `shortcut` and never count as escapes.

| agent | levels escaped (latest) | honest runs cancelled (all runs) | mean effort vs human min | mean recall | total cost |
|-------|------------------------|----------------------------------|--------------------------|-------------|------------|
| h/web-surfer-pro | 5/5 | 24/29 | +4 | 0.62 | $0.27 |
| h/web-surfer-flash | 5/5 | 14/15 | +1 | 0.87 | $0.12 |

With a raised step budget (50 for cancel/unsubscribe), pro escaped L5 twice more — 11/9 effort in 73s and 21/9 in 148s — and flash escaped it in 12/9. The L5 escape path is real but buried: retention chat → "Go to my account" → paused page → the small "I asked to cancel, not pause" link → confirm. Agents that find both hidden elements win; the chat loop eats the step budget for the rest.

## Testing

```bash
bash scripts/test.sh      # pytest
bash scripts/rehearse.sh  # smoke test: pages + demo replay to batch_done
```

`scripts/serve.sh` / `scripts/test.sh` pin `UV_PROJECT_ENVIRONMENT=$HOME/.venvs/hcompany` (avoids the iCloud `UF_HIDDEN` `.venv` issue under `~/Documents`) — see AGENTS.md.
