"""Run persistence: audits, raw events and downscaled screenshots on disk."""

import hashlib
import io
import json
from pathlib import Path
from typing import Any, Literal

from PIL import Image

from escapehatch.models import Audit
from escapehatch.report import audit_to_json

Side = Literal["leave", "enter"]


class RunStore:
    def __init__(self, root: Path | str = "runs") -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "shots").mkdir(exist_ok=True)

    def _audit_dir(self, audit_id: str) -> Path:
        return self.root / audit_id

    def save_audit(self, audit: Audit) -> Path:
        d = self._audit_dir(audit.id)
        d.mkdir(parents=True, exist_ok=True)
        path = d / "audit.json"
        path.write_text(audit_to_json(audit))
        return path

    def load_audit(self, audit_id: str) -> Audit:
        return Audit.model_validate_json((self._audit_dir(audit_id) / "audit.json").read_text())

    def list_audits(self) -> list[str]:
        ids = [
            p.name
            for p in self.root.iterdir()
            if p.is_dir() and (p / "audit.json").exists()
        ]
        return sorted(ids, key=lambda i: (self._audit_dir(i) / "audit.json").stat().st_mtime, reverse=True)

    def save_events(self, audit_id: str, side: Side, events: list[dict[str, Any]]) -> Path:
        d = self._audit_dir(audit_id)
        d.mkdir(parents=True, exist_ok=True)
        path = d / f"events_{side}.json"
        path.write_text(json.dumps(events, indent=2, ensure_ascii=False))
        return path

    def load_events(self, audit_id: str, side: Side) -> list[dict[str, Any]]:
        return json.loads((self._audit_dir(audit_id) / f"events_{side}.json").read_text())

    @staticmethod
    def _shot_name(url: str) -> str:
        return hashlib.sha1(url.encode()).hexdigest() + ".jpg"

    def save_screenshot(self, url: str, png_bytes: bytes) -> Path:
        """Downscale to max width 900 and store as JPEG q78."""
        img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
        if img.width > 900:
            h = round(img.height * 900 / img.width)
            img = img.resize((900, h), Image.LANCZOS)
        path = self.root / "shots" / self._shot_name(url)
        img.save(path, "JPEG", quality=78)
        return path

    def local_shot(self, url: str | None) -> Path | None:
        if not url:
            return None
        path = self.root / "shots" / self._shot_name(url)
        return path if path.exists() else None
