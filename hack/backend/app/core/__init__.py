"""FakeAI helpers used when FAKE_AI=1 — deterministic, no network."""
from __future__ import annotations

FAKE_ON = ("escalade", "bloc", "cuisine", "ramen", "recette", "japonais", "grimpe")
FAKE_OFF = ("drama", "gaming", "fortnite", "célébrité", "politique", "minecraft")


def fake_verdict(title: str, hashtags: list[str]) -> tuple[str, float, str]:
    text = (title + " " + " ".join(hashtags)).lower()
    on_hits = [k for k in FAKE_ON if k in text]
    off_hits = [k for k in FAKE_OFF if k in text]
    if off_hits:
        return "off", 0.92, f"Hors sujet : {off_hits[0]}"
    if on_hits:
        return "on", 0.9, f"Dans le sujet : {on_hits[0]}"
    return "unsure", 0.4, "Pas assez d'indices"
