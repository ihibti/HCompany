"""Holo LLM via the OpenAI-compatible H Models API."""
from __future__ import annotations

import json
from typing import Any

from openai import OpenAI
from pydantic import BaseModel

from app.config import get_settings


def get_client() -> OpenAI:
    s = get_settings()
    return OpenAI(base_url="https://api.hcompany.ai/v1/", api_key=s.hai_api_key)


def chat_structured(
    model: str,
    schema: type[BaseModel],
    messages: list[dict[str, str]],
    reasoning_effort: str | None = "none",
    client: OpenAI | None = None,
) -> BaseModel:
    """One structured chat call. reasoning_effort 'none' disables thinking."""
    client = client or get_client()
    kwargs: dict[str, Any] = {}
    if reasoning_effort is not None:
        kwargs["extra_body"] = {"reasoning_effort": reasoning_effort}
    resp = client.chat.completions.create(
        model=model,
        temperature=0,
        response_format={"type": "json_schema",
                         "json_schema": {"name": schema.__name__.lower(), "schema": schema.model_json_schema()}},
        messages=messages,
        **kwargs,
    )
    return schema.model_validate(json.loads(resp.choices[0].message.content))
