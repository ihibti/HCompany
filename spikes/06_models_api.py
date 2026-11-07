"""Spike 6: Models API — list models, classify a screenshot for dark patterns.

1. GET /v1/models -> save raw list.
2. Pick a downloaded screenshot (spikes/out/screenshots/) and send it to a Holo
   model asking to classify dark patterns.
3. Try response_format={"type":"json_schema",...}; if it fails, plain JSON prompt.
"""

import base64
import json
import os
import sys
from pathlib import Path

import httpx
from openai import OpenAI

sys.path.insert(0, str(Path(__file__).parent))
from common import OUT_DIR, save_json

API = "https://api.hcompany.ai/v1"
SCREEN_DIR = OUT_DIR / "screenshots"

PROMPT = (
    "This is a screenshot of a website cookie consent banner. "
    "Identify any dark patterns present (e.g. pre-ticked boxes, asymmetric "
    "button styling, confirmshaming, hidden reject option, forced action). "
    "Return JSON with keys: has_banner (bool), dark_patterns (list of strings), "
    "asymmetry_notes (string), confidence (number 0-1)."
)

SCHEMA = {
    "type": "object",
    "properties": {
        "has_banner": {"type": "boolean"},
        "dark_patterns": {"type": "array", "items": {"type": "string"}},
        "asymmetry_notes": {"type": "string"},
        "confidence": {"type": "number"},
    },
    "required": ["has_banner", "dark_patterns", "asymmetry_notes", "confidence"],
    "additionalProperties": False,
}


def pick_screenshot() -> Path | None:
    env = os.environ.get("SPIKE_SHOT")
    if env:
        p = Path(env)
        return p if p.exists() else None
    pngs = sorted(SCREEN_DIR.glob("*.png")) if SCREEN_DIR.exists() else []
    return pngs[0] if pngs else None


def data_uri(path: Path) -> str:
    b64 = base64.b64encode(path.read_bytes()).decode()
    return f"data:image/png;base64,{b64}"


def main() -> None:
    key = os.environ["HAI_API_KEY"]
    client = OpenAI(base_url=f"{API}/", api_key=key)

    # 1. List models
    models = client.models.list()
    model_list = [m.model_dump(mode="json") for m in models.data]
    save_json("06_models.json", model_list)
    print("models:", [m["id"] for m in model_list])

    shot = pick_screenshot()
    if shot is None:
        print("NO SCREENSHOT FOUND — run spike 2 first. Skipping classification.")
        return
    print("using screenshot:", shot, f"({shot.stat().st_size} bytes)")
    img = data_uri(shot)

    # choose a vision model: prefer holo4-35b-a3b (the flash agent's model),
    # or SPIKE_MODEL to override
    model_id = os.environ.get("SPIKE_MODEL", "holo4-35b-a3b")
    if not any(m["id"] == model_id for m in model_list):
        model_id = model_list[0]["id"]
    print("model:", model_id)

    # 2. Try response_format json_schema
    try:
        resp = client.chat.completions.create(
            model=model_id,
            messages=[{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": img}},
                {"type": "text", "text": PROMPT},
            ]}],
            response_format={"type": "json_schema", "json_schema": {"name": "dark_patterns", "schema": SCHEMA, "strict": True}},
            temperature=0.0,
            max_tokens=1024,
        )
        content = resp.choices[0].message.content
        save_json(f"06_classify_{model_id}_json_schema.json", {
            "model": model_id, "response_format": "json_schema",
            "content": content, "usage": resp.usage.model_dump(mode="json") if resp.usage else None,
        })
        print("json_schema OK:", content[:500])
        return
    except Exception as ex:
        print("json_schema FAILED:", type(ex).__name__, str(ex)[:500])
        save_json("06_classify_json_schema_error.json", {"error": f"{type(ex).__name__}: {ex}"})

    # 3. Fallback: plain JSON prompting
    try:
        resp = client.chat.completions.create(
            model=model_id,
            messages=[{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": img}},
                {"type": "text", "text": PROMPT + " Respond with ONLY a JSON object, no markdown fences."},
            ]}],
            temperature=0.0,
            max_tokens=1024,
        )
        content = resp.choices[0].message.content
        save_json(f"06_classify_{model_id}_plain.json", {
            "model": model_id, "response_format": "plain_prompt",
            "content": content, "usage": resp.usage.model_dump(mode="json") if resp.usage else None,
        })
        print("plain prompt result:", content[:500])
    except Exception as ex:
        print("plain prompt FAILED:", type(ex).__name__, str(ex)[:500])
        save_json("06_classify_plain_error.json", {"error": f"{type(ex).__name__}: {ex}"})


if __name__ == "__main__":
    main()
