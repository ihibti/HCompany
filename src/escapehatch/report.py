"""Pure HTML/JSON report rendering for an Audit."""

import json
from collections.abc import Callable
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from escapehatch.models import Audit

_TEMPLATE_DIR = Path(__file__).parent / "templates"


def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(_TEMPLATE_DIR),
        autoescape=select_autoescape(["html"]),
    )


def render_report_html(audit: Audit, screenshot_resolver: Callable[[str | None], str | None]) -> str:
    """Render a standalone dark-themed report page. screenshot_resolver maps a
    platform screenshot URL (or None) to a displayable URL/path (or None)."""
    template = _env().get_template("report.html")
    return template.render(audit=audit, shot=screenshot_resolver)


def audit_to_json(audit: Audit) -> str:
    return audit.model_dump_json(indent=2)
