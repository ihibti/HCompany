/* Escape Hatch race view: live + replay batches over SSE */
(function () {
  const { batchId, kind } = window.RACE;
  const cols = {};

  function col(run) {
    if (!cols[run]) {
      const el = document.querySelector(`.race-col[data-run="${CSS.escape(run)}"]`);
      if (!el) return null;
      cols[run] = {
        run,
        el,
        status: el.querySelector('[data-role="status"]'),
        screen: el.querySelector('[data-role="screen"]'),
        empty: el.querySelector('[data-role="empty"]'),
        img: el.querySelector('[data-role="img"]'),
        marker: el.querySelector('[data-role="marker"]'),
        caption: el.querySelector('[data-role="caption"]'),
        outEffort: el.querySelector('[data-role="outEffort"]'),
        inEffort: el.querySelector('[data-role="inEffort"]'),
        outUnit: el.querySelector('[data-role="outUnit"]'),
        inUnit: el.querySelector('[data-role="inUnit"]'),
        phase: el.querySelector('[data-role="phase"]'),
        findings: el.querySelector('[data-role="findings"]'),
        steps: el.querySelector('[data-role="steps"]'),
        controls: el.querySelector('[data-role="controls"]'),
        done: el.querySelector('[data-role="done"]'),
        grade: el.querySelector('[data-role="grade"]'),
        headline: el.querySelector('[data-role="headline"]'),
        report: el.querySelector('[data-role="report"]'),
        lastShot: null,
        lastClick: null,
        stepCount: { leave: 0, enter: 0 },
        finished: { leave: false, enter: false },
        hasEnter: false,
      };
      bindControls(cols[run]);
    }
    return cols[run];
  }

  function setStatus(c, text) {
    const map = {
      queued: "", running: "running", paused: "paused",
      awaiting_tool_results: "awaiting_tool_results",
      completed: "completed", failed: "failed", timed_out: "failed",
      interrupted: "failed", idle: "running", classifying: "classifying",
      replay: "running", done: "done", retrying: "retrying",
    };
    c.status.textContent = text;
    c.status.className = "status-pill " + (map[text] || "");
    c.el.classList.toggle("running", ["running", "awaiting_tool_results", "classifying", "replay"].includes(text));
  }

  function shotUrl(step) {
    const u = step && step.screenshot_url;
    return u ? EH.shotSrc(u) : null;
  }

  function showShot(c, step, journey) {
    if (journey !== "leave") return; // main screen follows the leave journey
    const src = shotUrl(step);
    if (!src || src === c.lastShot) return;
    c.lastShot = src;
    const img = c.img;
    img.classList.remove("loaded");
    img.onload = () => img.classList.add("loaded");
    img.onerror = () => { img.hidden = true; c.empty.hidden = false; c.empty.querySelector(".screen-empty-text").textContent = "screenshot unavailable"; };
    img.src = src;
    img.hidden = false;
    c.empty.hidden = true;
  }

  function updateMarker(c, step) {
    const args = step.args || {};
    if (step.action === "click_web" && typeof args.x === "number" && typeof args.y === "number") {
      c.lastClick = { x: args.x, y: args.y };
    }
    if (!c.lastClick) return;
    c.marker.style.left = (c.lastClick.x * 100) + "%";
    c.marker.style.top = (c.lastClick.y * 100) + "%";
    c.marker.hidden = false;
  }

  function captionFor(step) {
    const el = step.element ? ` “${step.element}”` : "";
    const verb = {
      click_web: "Clicking", write: "Typing into", press_keys_web: "Pressing keys on",
      go_to_web: "Opening", go_back_web: "Going back", scroll_web: "Scrolling",
      web_search: "Searching", web_fetch: "Fetching", request_confirmation: "Asking for confirmation",
      drag_and_drop_web: "Dragging", select_option: "Selecting", refresh_web: "Reloading",
      wait_web: "Waiting", switch_tab_web: "Switching tab", close_tab_web: "Closing tab",
      ctrl_f_web: "Find in page", move_mouse_web: "Moving mouse", reader_mode: "Reader mode",
      find_in_page: "Find in page", switch_chunk: "Switching chunk",
      fill_secret_at: "Filling credentials", answer: "Answering",
    }[step.action] || step.action;
    return `${verb}${el}`;
  }

  function stepLabel(step) {
    const a = step.args || {};
    const el = step.element || "";
    switch (step.action) {
      case "click_web": return `Click · '${el || "element"}'`;
      case "write":
      case "fill_secret_at": return `Type · '${a.text || a.value || el}'`;
      case "go_to_web": {
        const u = a.url || "";
        try { const p = new URL(u); return `Go to · ${p.host}${p.pathname}`; }
        catch { return `Go to · ${u}`; }
      }
      case "scroll_web": return "Scroll";
      case "wait_web": return "Wait";
      case "press_keys_web": return `Press · ${a.keys || ""}`;
      case "web_search": return `Search the web · ${a.query || ""}`;
      case "request_confirmation": return "Asked for confirmation";
      case "go_back_web": return "Go back";
      case "refresh_web": return "Reload";
      case "drag_and_drop_web": return `Drag · '${el}'`;
      case "select_option": return `Select · '${el || a.option || ""}'`;
      case "ctrl_f_web":
      case "find_in_page": return `Find · ${a.query || a.text || ""}`;
      case "switch_tab_web": return "Switch tab";
      case "close_tab_web": return "Close tab";
      case "move_mouse_web": return "Move mouse";
      case "answer": return "Answered";
      default: return step.action || "step";
    }
  }

  function addStep(c, msg) {
    const step = msg.step || {};
    const journey = msg.journey;
    c.stepCount[journey] = (c.stepCount[journey] || 0) + 1;
    if (journey === "enter") c.hasEnter = true;

    if (journey === "leave") {
      showShot(c, step, journey);
      updateMarker(c, step);
      c.caption.textContent = captionFor(step);
      c.outEffort.textContent = msg.effort_so_far ?? c.outEffort.textContent;
      if (msg.effort_so_far != null) c.outUnit.textContent = msg.effort_so_far === 1 ? "action" : "actions";
    } else {
      c.inEffort.textContent = msg.effort_so_far ?? c.inEffort.textContent;
      if (msg.effort_so_far != null) c.inUnit.textContent = msg.effort_so_far === 1 ? "action" : "actions";
    }

    const li = document.createElement("li");
    li.innerHTML =
      `<span class="t-idx">#${step.index ?? ""}</span>` +
      `<span class="t-action">${escapeHtml(stepLabel(step))}</span>` +
      `<span class="t-el">${escapeHtml(step.element || step.args?.url || "")}</span>`;
    if (step.reasoning || step.message) {
      const det = document.createElement("details");
      det.innerHTML = `<summary>why</summary><div class="t-reason">${escapeHtml(step.reasoning || step.message || "")}</div>`;
      li.appendChild(det);
    }
    c.steps.prepend(li);
    while (c.steps.children.length > 60) c.steps.lastChild.remove();
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
  }

  function addFinding(c, f) {
    const card = document.createElement("div");
    card.className = `finding-card sev-${f.severity || 2}`;
    card.innerHTML =
      `<div class="finding-name">${escapeHtml((f.pattern || "").replace(/_/g, " "))}` +
      `<span class="sev">severity ${f.severity || "?"}</span></div>` +
      `<div class="finding-ev">“${escapeHtml(f.evidence || "")}”</div>`;
    c.findings.appendChild(card);
  }

  function showDone(c, msg) {
    showShot(c, msg, "leave");
    c.marker.hidden = true;
    c.caption.textContent = {
      success: "Completed", impossible: "Exit blocked", blocked: "Site access blocked",
      failed: "Inconclusive", not_applicable: "Not applicable",
    }[msg.outcome] || "Finished";
    c.done.hidden = false;
    c.phase.hidden = true;
    const g = c.grade;
    g.textContent = msg.grade || "?";
    g.className = "done-badge grade-" + (msg.grade || "?");
    g.hidden = false;
    if (msg.outcome === "impossible") {
      c.headline.textContent = "Impossible — the site blocks the exit (cookie wall / paywall / no refuse path).";
      c.headline.classList.add("impossible");
    } else {
      c.headline.textContent = msg.headline || "";
      c.headline.classList.remove("impossible");
    }
    c.report.href = "/audits/" + msg.audit_id;
    setStatus(c, "done");
    c.controls.hidden = true;
  }

  function clearReplayConfirms(c) {
    document.querySelectorAll('.confirm-modal.replay-auto')
      .forEach((m) => { if (m.dataset.run === c.run) m.remove(); });
  }

  function showConfirm(c, msg) {
    const stack = document.querySelector('[data-role="confirms"]');
    const modal = document.createElement("div");
    modal.dataset.run = c.run;
    if (msg.replay_auto) {
      modal.className = "confirm-modal replay-auto";
      modal.innerHTML =
        `<h3>The agent asked before acting</h3>` +
        `<p class="confirm-action">${escapeHtml(msg.action || "")}</p>` +
        `<div class="confirm-timer" style="color:var(--green)">auto-approved in replay</div>`;
      stack.appendChild(modal);
      setTimeout(() => modal.remove(), 30000);
      return;
    }
    modal.className = "confirm-modal";
    modal.innerHTML =
      `<h3>The agent is about to act</h3>` +
      `<p class="confirm-action">${escapeHtml(msg.action || "")}</p>` +
      `<p class="confirm-sub">This may be irreversible. ${msg.journey === "enter" ? "(enter journey)" : ""}</p>` +
      `<div class="confirm-timer">auto-denies in <b data-t>120</b>s</div>` +
      `<div class="confirm-btns">` +
      `<button class="approve" data-a="1">Approve</button>` +
      `<button class="deny" data-a="0">Deny</button></div>`;
    stack.appendChild(modal);
    let left = 120;
    const timerEl = modal.querySelector("[data-t]");
    const tick = setInterval(() => {
      left -= 1;
      timerEl.textContent = left;
      if (left <= 0) { clearInterval(tick); modal.remove(); }
    }, 1000);
    modal.querySelectorAll("button").forEach((b) => {
      b.addEventListener("click", async () => {
        clearInterval(tick);
        modal.remove();
        await fetch(`/api/audits/${encodeURIComponent(msg.run || c.run)}/confirm/${msg.id}`, {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ approved: b.dataset.a === "1" }),
        });
      });
    });
  }

  function bindControls(c) {
    c.controls.querySelectorAll("[data-ctrl]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const action = btn.dataset.ctrl === "stop" ? "stop" : btn.dataset.ctrl;
        for (const side of ["leave", "enter"]) {
          fetch(`/api/audits/${encodeURIComponent(c.run)}/${side}/${action}`, { method: "POST" }).catch(() => {});
        }
      });
    });
    const form = c.controls.querySelector('[data-role="msgform"]');
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const input = form.querySelector('[data-role="msginput"]');
      const text = input.value.trim();
      if (!text) return;
      input.value = "";
      for (const side of ["leave", "enter"]) {
        fetch(`/api/audits/${encodeURIComponent(c.run)}/${side}/message`, {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text }),
        }).catch(() => {});
      }
    });
  }

  function handle(msg) {
    if (msg.type === "batch") {
      document.getElementById("raceMeta").textContent =
        `${msg.audits.length} audit${msg.audits.length > 1 ? "s" : ""} · ${msg.kind}`;
      return;
    }
    const run = msg.run;
    if (!run) return;
    const c = col(run);
    if (!c) return;
    if (c.status.textContent === "queued" && (
      msg.type === "step" || msg.type === "confirm_request" ||
      (msg.type === "status" && msg.status && msg.status !== "queued")
    )) {
      setStatus(c, "running");
    }
    if (msg.type === "step" || msg.type === "status") clearReplayConfirms(c);
    switch (msg.type) {
      case "step": addStep(c, msg); break;
      case "status":
        if (msg.journey === "audit") {
          if (msg.status === "classifying") {
            c.phase.hidden = false;
            c.phase.textContent = msg.screenshots
              ? `Reviewing ${msg.screenshots} screenshots for dark patterns…`
              : "Reviewing screenshots for dark patterns…";
            setStatus(c, "classifying");
          }
        } else if (msg.journey === "enter") {
          // the column pill tracks the leave journey; enter only feeds counters
        } else if (msg.status === "completed" || msg.outcome) {
          setStatus(c, msg.outcome === "failed" ? "failed" : "completed");
        } else {
          setStatus(c, msg.status);
        }
        break;
      case "phase":
        if (msg.phase === "classifying") {
          c.phase.hidden = false;
          c.phase.textContent = msg.screenshots
            ? `Reviewing ${msg.screenshots} screenshots for dark patterns…`
            : "Reviewing screenshots for dark patterns…";
          setStatus(c, "classifying");
        }
        break;
      case "confirm_request": showConfirm(c, { ...msg, run }); break;
      case "finding": addFinding(c, msg.finding); break;
      case "done": showDone(c, msg); break;
      case "error":
        c.phase.hidden = false;
        c.phase.textContent = "Error: " + (msg.message || "unknown");
        break;
      case "batch_done": break;
      case "ping": break;
    }
  }

  // connect
  const es = new EventSource(`/api/batches/${encodeURIComponent(batchId)}/events`);
  let lastSeq = -1;
  es.onmessage = (ev) => {
    let msg;
    try { msg = JSON.parse(ev.data); } catch { return; }
    if (typeof msg.seq === "number") {
      if (msg.seq <= lastSeq) return;
      lastSeq = msg.seq;
    }
    handle(msg);
    if (msg.type === "batch_done") es.close();
  };
  es.onerror = () => { /* EventSource auto-reconnects; server replays history */ };
})();
