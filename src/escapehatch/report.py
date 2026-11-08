"""Pure HTML/JSON report rendering for an Audit."""

import json
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlparse

from jinja2 import Environment, FileSystemLoader, select_autoescape

from escapehatch.models import Audit, Step

_TEMPLATE_DIR = Path(__file__).parent / "templates"


def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(_TEMPLATE_DIR),
        autoescape=select_autoescape(["html"]),
    )


def step_label(step: Step) -> str:
    """Human-readable action label, e.g. "Click · 'Confirm'"."""
    a = step.args or {}
    el = step.element or ""
    action = step.action
    if action == "click_web":
        return f"Click · '{el or 'element'}'"
    if action in ("write", "fill_secret_at"):
        return f"Type · '{a.get('text') or a.get('value') or el}'"
    if action == "go_to_web":
        u = a.get("url") or step.url or ""
        try:
            p = urlparse(u)
            u = p.netloc + p.path
        except Exception:
            pass
        return f"Go to · {u}"
    if action == "scroll_web":
        return "Scroll"
    if action == "wait_web":
        return "Wait"
    if action == "press_keys_web":
        return f"Press · {a.get('keys') or ''}"
    if action == "web_search":
        return f"Search the web · {a.get('query') or ''}"
    if action == "request_confirmation":
        return "Asked for confirmation"
    if action == "go_back_web":
        return "Go back"
    if action == "refresh_web":
        return "Reload"
    if action == "drag_and_drop_web":
        return f"Drag · '{el}'"
    if action == "select_option":
        return f"Select · '{el or a.get('option') or ''}'"
    if action in ("ctrl_f_web", "find_in_page"):
        return f"Find · {a.get('query') or a.get('text') or ''}"
    if action == "switch_tab_web":
        return "Switch tab"
    if action == "close_tab_web":
        return "Close tab"
    if action == "move_mouse_web":
        return "Move mouse"
    if action == "answer":
        return "Answered"
    return action or "step"


def render_report_html(audit: Audit, screenshot_resolver: Callable[[str | None], str | None]) -> str:
    """Render a standalone dark-themed report page. screenshot_resolver maps a
    platform screenshot URL (or None) to a displayable URL/path (or None)."""
    template = _env().get_template("report.html")
    return template.render(audit=audit, shot=screenshot_resolver, step_label=step_label)


def audit_to_json(audit: Audit) -> str:
    return audit.model_dump_json(indent=2)
