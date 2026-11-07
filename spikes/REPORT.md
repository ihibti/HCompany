# Spike report — H Agents API for Escape Hatch

Date: 2026-11-07. SDK: `hai-agents==1.4.3` (uv project, Python 3.12). Region: EU (`Client()` defaults to `https://agp.eu.hcompany.ai`; `HaiAgentsEnvironment.US` → `agp.hcompany.ai`). Auth: `HAI_API_KEY` bearer.

Sessions consumed: **7** (budget ~10). All raw JSON under `spikes/out/`; screenshots under `spikes/out/screenshots/` (PNGs gitignored).

## TL;DR

- The Agents API does everything we need: structured answers, full event streams with screenshots + per-step URLs, custom tools with an approve/reject gate, 3-way concurrency on the free plan, per-step cost metrics.
- **`h/web-surfer-flash` (holo4-35b-a3b) is unreliable on adversarial cookie banners** — it fell into a 38-step tool-validation-error loop on lemonde.fr and never clicked anything. `h/web-surfer-pro` (holo4-27b) worked: 25 steps, $0.18, correctly diagnosed that lemonde.fr has *no refuse button at all*.
- `response_format={"type":"json_schema"}` **works** on the Models API — dark-pattern classification returns schema-valid JSON.
- **No `LiveViewUrlEvent` was emitted in any of the 7 sessions**, and `agent_view_url` (platform.hcompany.ai) sends `X-Frame-Options: DENY` + CSP `frame-ancestors 'none'` → **not iframe-embeddable**. Fallback (screenshot stream from events) is proven and cheap.
- lemonde.fr is a genuine Hall of Shame candidate: cookie wall with only "Accepter et continuer" / "S'abonner", refuse path buried in footer, re-shows banner for non-subscribers.

## 1. Cookie-refusal sessions with `answer_schema`

Prompt: *"Go to https://www.lemonde.fr and refuse all non-essential cookies with the fewest clicks possible. Do not accept any cookies. Report each click you made."* with `max_steps=40, max_time_s=420` and a Pydantic `CookieRefusal(clicks:int, steps:list[str], refused:bool, notes:str)`.

| Agent | Model | Wall | Steps | Events | Cost (MetricsUpdateEvent) | Result |
|---|---|---|---|---|---|---|
| `h/web-surfer-flash` | holo4-35b-a3b | 136.0s | 40 (hit cap) | 90 | **$0.0595** (869,695 in / 815,232 cached / 9,361 out) | `refused=false`; stuck in `scroll_web` validation-error loop, 0 clicks |
| `h/web-surfer-pro` | holo4-27b | 168.7s | 25 | 100 | **$0.1758** (684,652 in / 429,600 cached / 18,854 out) | `refused=false`, 3 clicks; proved no refuse button exists |

- Banner **did appear** in the cloud browser (EU region — screenshot evidence in `spikes/out/screenshots/bfa592c9_step1.png`, classified by Holo as `has_banner=true` + asymmetric buttons / hidden reject).
- `h/browser` env spec: `kind=web, host=cloud, mode={type:visual,width:1200,height:1200,markdown:false}, network=null` (default egress, no proxy). `start_url` defaults to bing.com — the agent navigates away itself.
- `run_session` returned `status=idle`; the session completed moments later (`AgentCompletionEvent`, final `/status` = `completed`). See gotchas.
- Pro's click trail (from `policy_event.tool_reqs`): `go_to_web` → `click_web` ("S'abonner", mistaken) → `go_back_web` → `go_to_web /gestion-des-cookies/` → `click_web` footer "Gestion des cookies" → `click_web` "Retirer mon consentement". It also used `web_search`, `web_fetch`, `drag_and_drop_web`, `press_keys_web`, `scroll_web`.
- Action arg shapes observed: `click_web {x:0.498, y:0.709, element:"<description>"}` (normalized coords + grounding description), `scroll_web {direction, num_pixels, scroll_element|null|{element,x,y} in [0,1000]}`, `go_to_web {url}`, `answer {…schema fields…}`.
- Raw: `spikes/out/01_h_web-surfer-flash.json`, `spikes/out/01_h_web-surfer-pro.json`.

## 2. Session events

`client.sessions.list_session_events(session_id, page=1, size=200)` → page envelope `{items, page, total}`, oldest first. Raw dumps: `spikes/out/02_events_<sid8>.json` for 4 sessions (flash, pro, leboncoin, marmiton).

Confirmed shapes:
- Envelope `{type, data, timestamp}`; `AgentEvent.data` discriminated by `kind`: `policy_event` (reasoning_content, content, `tool_reqs[{tool_name,args,id}]`, validation_errors), `observation_event` (`type:"web"`, `image`, `metadata`), `tool_result`, `answer_event`, `error_event`, `message_event`, `flow_event`.
- `observation_event.metadata`: `url, title, text (empty unless markdown:true), tabs, current_tab, viewport_size, page_size, scroll_position, cursor_position` — **per-step URL confirmed**.
- `MetricsUpdateEvent` emitted **per step** (cumulative): `data.metrics.{steps,total_cost,input_cost,output_cost,reasoning_cost,cost_per_model[]}`.
- Screenshots: `image = {source: "https://agp.eu.hcompany.ai/api/v1/trajectories/<sid>/resources/<bucket>/<key>", type:"url", media_type:"image/png"}`. **`source` requires auth**: no header → `404`; `Authorization: Bearer $HAI_API_KEY` → `200 image/png`. Also downloadable via `client.sessions.get_session_resource(sid, bucket, key)` → iterator of bytes (verified, 263,724-byte PNG). Bucket is an ugly auto name (`production-eu-agentplatfo-screenshotbucketv2f6e481-…`); parse it out of `image.source`.
- Downloaded 9 screenshots total to `spikes/out/screenshots/` (bing start page + lemonde banner + leboncoin + marmiton steps).

## 3. Live view / iframe

- **No `LiveViewUrlEvent` in any of the 7 sessions** (all `h/web-surfer-*` on `h/browser`). The event type exists in the SDK (`LiveViewUrlEvent`, `data.live_view_url`) but didn't fire — possibly only for desktop/other envs or headed modes.
- `session.agent_view_url` = `https://platform.hcompany.ai/agents/sessions/<id>` → headers: `x-frame-options: DENY`, CSP `frame-ancestors 'none'` → **cannot be iframed**.
- `client.sessions.share_session(id)` → `{share_url: "/share/api/v1/trajectories/<id>"}` (public, no key) — but it returns **JSON trajectory data, not HTML**; the UI still lives on platform.hcompany.ai. Unshared afterwards.
- **Conclusion: no embeddable live view.** Fallback = poll `list_session_events`/`changes` and serve `image.source` screenshots (auth'd download, ~260KB each) — exactly what our `events.py`/`server.py` plan already assumes.

## 4. Custom tools

```python
def request_confirmation(action: str) -> str:
    """Ask the user to approve an action before it is performed. ..."""
    return "approved"

client.run_session(agent=..., messages=..., tools=[request_confirmation], ...)
```

- Schema derived from signature + docstring; confirmed registered on the session request (`request.agent.tools[]` shows `request_confirmation` with JSON schema).
- With `h/web-surfer-flash`: tool registered but **never called** (model stuck in error loop, see §1).
- With `h/web-surfer-pro`: **called once**, agent went `awaiting_tool_results` → SDK auto-ran the function → `tool_result "approved"` → session resumed. Evidence: `ActiveStateChangeEvent{state:"awaiting_tool_results", pending_tool_calls:[{tool_name:"request_confirmation", args:{action:"Click the 'ACTIVÉ' toggle…"}, id:"chatcmpl-tool-…"}]}` then `TOOL_RESULT: request_confirmation -> approved`. Raw: `spikes/out/04_custom_tool_h_web-surfer-pro.json`, call log `spikes/out/04_tool_calls.jsonl`.
- Note: `run_session`/`stream` executes tool calls **in-process while waiting** — the function must be importable in the same process. At-least-once execution; make side-effecting tools idempotent.

## 5. Concurrency + quotas

- `client.sessions.get_session_quota()` → `{scope:"org", limit:3, active:N, available:3-N}` — **free plan = 3 concurrent**. Over limit → sessions `queued` (default `queue:true`), start oldest-first.
- `client.quota.get_token_quota()` → `{limit:60_000_000, used:~950K, remaining:~59M, window_start/end}` — free plan 60M tokens/month.
- 3 parallel `AsyncClient().run_session(...)` (lemonde, leboncoin, marmiton) via `asyncio.gather`: **all ran concurrently**, total wall 71.0s = slowest session. Per-site: marmiton 23.8s/$0.0052 (1 click, "Je n'accepte rien"), leboncoin 32.4s/$0.0104 (2 clicks, "Continuer sans accepter" → "I refuse"), lemonde 71.0s (flash, failed as in §1). Raw: `spikes/out/05_parallel.json`, `05_quota.json`.
- Plans (docs): Free 3 concurrent/60M tok; Builder $20/mo 10 concurrent/1B; Startup $200/mo 100 concurrent/10B. Cloud env starts capped at 10/min/user.

## 6. Models API (OpenAI-compatible, `https://api.hcompany.ai/v1`)

- `GET /v1/models` → 4 models: `holo3-1-35b-a3b`, `holo3-122b-a10b` (no tools), `holo4-27b`, `holo4-35b-a3b`. Raw: `spikes/out/06_models.json`. Pricing (per M tok): holo4-35b-a3b $0.30/$2.00, holo4-27b $0.40/$3.00 (in/out); cache reads ~10× cheaper.
- Screenshot → chat completion with `image_url` data-URI works (PNG base64, ~1.5K prompt tokens incl. ~1.4K image tokens).
- **`response_format={"type":"json_schema","json_schema":{"name":...,"schema":...,"strict":true}}` WORKS** on holo4-27b and holo4-35b-a3b — returned schema-valid JSON, no fences. Plain-JSON prompting also works (needs `.strip()`/parse; occasional leading blank lines).
- Dark-pattern classification of the real lemonde banner screenshot: both models flagged `has_banner=true`, `asymmetric button styling`, `hidden reject option`/`forced action`, with sensible `asymmetry_notes`. ~400-1900 completion tokens, ~$0.001-0.002/call. Raw: `spikes/out/06_classify_holo4-27b.json`, `06_classify_holo4-35b-a3b.json`.
- Holo-specific extras: `structured_outputs={"json": <schema>}` via `extra_body`, `reasoning_effort`, `chat_template_kwargs.enable_thinking`, `top_k` via extra_body.

## 7. SDK control methods (inspected, not all exercised)

All present on `hai_agents.polling.SessionHandle` (from `client.start_session(...)` or `client.session(id)`):

- `send_message(message)` — str or `SendSessionMessagesRequestBody_UserMessage`
- `pause()`, `resume()`, `cancel()`, `force_answer()`
- `stream(from_index=0, wait_for_seconds=20, limit=None, until="settled"|"terminal", timeout_seconds=None, tools=None)` — yields events, auto-answers tool calls
- `wait_for_completion(**kwargs)` → `SessionRunResult` (`.id .status .events .answer .outcome .error .error_code .final_changes`)
- `status()`, `changes(from_index=0,...)`, `get()`

Raw client equivalents: `sessions.send_session_messages/pause_session/resume_session/cancel_session/force_session_answer`, plus `create_session`, `get_session`, `get_session_status`, `get_session_changes`, `list_session_events`, `get_session_quota`, `get_session_resource`, `share_session`/`unshare_session`, `send_session_tool_results`, feedback endpoints. `Client.run_session(...)` = create+wait convenience. Full dump: `spikes/out/07_sdk_methods.json`.

## Gotchas

1. **flash model loops on schema-invalid tool args.** `scroll_web.scroll_element` must be `{element,x,y}` object or null; holo4-35b-a3b emitted a bare string ~38× → `error_event`s until `max_steps`. Always set `max_steps`/`max_time_s`. pro (holo4-27b) is the reliable choice for adversarial UIs; flash is fine for easy sites (marmiton 1 click/$0.005, leboncoin 2 clicks/$0.010).
2. `run_session` settles on `idle` too — check `result.status`/final `/status` for the true terminal state; `AgentCompletionEvent` confirms completion.
3. `metadata.text` is empty unless env `mode.markdown=true` — for text evidence enable it or rely on screenshots + `metadata.url`.
4. Screenshot `image.source` URLs are auth-gated (404 without bearer). Use `get_session_resource` or pass the header.
5. No live-view iframe → build the live feed from events + screenshots (poll `changes` with `wait_for_seconds` long-poll, or `stream()`).
6. Custom tools run client-side inside `stream()`/`run_session` — keep the process alive; calls are at-least-once.
7. `answer_schema` must be a Pydantic `BaseModel`; don't also set `overrides["agent.answer_format"]` (SDK rejects the pair). Answer failures → `error_code: answer_validation`.
8. Cloud browser start rate limit: 10 env starts/min/user — spread big batches.

## Files

- `spikes/01_cookie_refusal.py`, `02_events_dump.py`, `03_liveview.py`, `04_custom_tool.py`, `05_parallel.py`, `06_models_api.py`, `07_sdk_methods.py`, `common.py`
- `spikes/out/*.json` — raw evidence; `spikes/out/screenshots/*.png` — gitignored
