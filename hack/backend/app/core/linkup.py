"""Linkup search wrappers (sync — callers use asyncio.to_thread)."""
from __future__ import annotations

from typing import Any

from linkup import LinkupClient
from pydantic import BaseModel

from app.config import get_settings


def get_client() -> LinkupClient:
    return LinkupClient(api_key=get_settings().linkup_api_key)


def search_structured(query: str, schema: type[BaseModel], depth: str = "standard",
                      client: LinkupClient | None = None) -> tuple[BaseModel, list[dict[str, str]]]:
    client = client or get_client()
    resp = client.search(query=query, depth=depth, output_type="structured",
                         structured_output_schema=schema, include_sources=True)
    data: Any = getattr(resp, "data", resp)
    sources = [{"name": getattr(s, "name", ""), "url": getattr(s, "url", "")}
               for s in getattr(resp, "sources", []) or []]
    return schema.model_validate(data), sources


def search_results(query: str, depth: str = "fast", max_results: int = 5,
                   client: LinkupClient | None = None) -> list[dict[str, str]]:
    client = client or get_client()
    resp = client.search(query=query, depth=depth, output_type="searchResults",
                         max_results=max_results)
    out = []
    for r in getattr(resp, "results", []) or []:
        out.append({"name": getattr(r, "name", ""), "url": getattr(r, "url", ""),
                    "content": getattr(r, "content", "")})
    return out
