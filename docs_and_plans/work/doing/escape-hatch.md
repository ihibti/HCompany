# Escape Hatch: how hard is it to leave?

A computer-use agent that tries to *leave*: refuse cookies, unsubscribe, cancel a subscription, delete an account. It measures how much friction the site puts in the way, catches the dark patterns on screen with screenshot evidence, and writes a report that cites the relevant law. In consumer mode it does the leaving for you and asks before anything irreversible.

## Why this fits the hackathon
- **Native to computer use:** exit flows have no API by design. They are adversarial UIs built to confuse automation and humans alike. A DOM scraper can't judge whether "Reject" is harder to find than "Accept"; vision can.
- **Useful, with money behind it:**
  - B2B compliance audits. CNIL has fined Google and Meta because refusing was harder than accepting. France's 2023 "résiliation en 3 clics" law, EU DSA Art. 25, the FTC click-to-cancel rule.
  - Buyers: consumer associations (UFC-Que Choisir), regulators, and brands that want to pre-audit themselves.
  - Consumer cancel-for-me, like Rocket Money but working on any site.
- **Original and playful:** a "Hall of Shame" leaderboard of real sites, and an evil mock streaming service ("Netflux") with gauntlet levels as a reliability benchmark.

## Judging map
| Criterion | Weight | How we score |
| - | - | - |
| Use of computer use | 25% | Live parallel agents on real sites; vision-based dark-pattern detection; the "accept" vs "leave" asymmetry measured by actually clicking |
| Execution / reliability | 25% | Gauntlet benchmark with a measured success rate; recorded-run replay as a fallback; tested pure core |
| Usefulness / impact | 20% | Legal hooks (CNIL, DGCCRF, DSA, FTC); report a compliance team can file |
| Originality | 15% | Agent vs. dark patterns, Hall of Shame |
| UX and user control | 10% | Live view, step feed, pause/stop/steer, confirmation before irreversible actions (custom tool) |
| Clarity | 5% | One-screen story: URL in → agent fights → report card out |

## Architecture
- `src/escapehatch/` (Python 3.12, uv)
  - `agent.py`: wraps hai-agents. `run_journey(url, task) -> Journey`. Custom tool `request_confirmation`. Structured answer schema.
  - `events.py`: **pure.** Raw session events → `Journey` (ordered steps: action, reasoning, screenshot ref, url).
  - `patterns.py`: Holo Models API classification of key screenshots → `DarkPattern` findings (type, evidence step, explanation).
  - `scoring.py`: **pure.** Friction score from clicks, asymmetry against the accept/signup path, pattern severity → grade A–F.
  - `legal.py`: **pure.** Pattern/task → applicable rule references.
  - `report.py`: **pure.** Journey + findings + score → HTML/JSON report card.
  - `store.py`: runs persisted under `runs/<id>/` (events.json, screenshots, report.json) so any run can be replayed offline.
  - `server.py`: FastAPI app: start audits, SSE live step feed, live view iframe, confirmation modal, pause/stop, Hall of Shame, replay mode.
- `gauntlet/`: static "Netflux" mock with levels 1–5 of increasing dark-pattern hostility (confirmshaming, hidden link, fake close button, retention offers, nag loops, a "chat with an agent to cancel" step). Hosted on GitHub Pages (public URL the cloud browser can reach). Success = landing on a final cancellation page with a token that our verifier checks.
- `tests/`: unit tests on the pure modules using recorded fixtures; gauntlet level verification.

## Demo script (3 minutes)
1. Hook: "Signing up takes 1 click. Leaving takes 14." Show the Hall of Shame.
2. Live: paste 3 real French sites → three agents race in parallel to refuse cookies; report cards appear with screenshot evidence and legal references.
3. Consumer mode: "Cancel my Netflux": the agent fights level 5, pauses to ask "This will cancel your plan. Confirm?", the user approves, done.
4. Reliability: gauntlet benchmark table (success rate per level and per agent model).
5. Business: B2B compliance audits plus a consumer plan.

## Overnight execution plan
1. API spike: sessions, events, screenshots, live view, custom tools, concurrency, Models API structured output. Report in `spikes/REPORT.md`.
2. Pure core with tests: events → journey, scoring, legal, report.
3. Gauntlet mock site with 5 levels, published to GitHub Pages.
4. Agent runner, pattern classifier, run store.
5. Web UI with live feed, live view, controls, report cards, Hall of Shame, replay.
6. Real-site runs to populate the Hall of Shame; gauntlet benchmark runs.
7. README, pitch script, slide outline, manual test checklist.
8. Final pass: full test suite, demo rehearsal from a cold start, push.

## Risks
- Live view may not be embeddable in an iframe → fallback: stream screenshots from events.
- Real sites change or block the cloud browser → recorded runs as replay fallback.
- Models API structured output may not be supported → plain JSON prompting with validation.
