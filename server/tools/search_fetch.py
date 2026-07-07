"""`search` + `fetch`: the tool pair ChatGPT deep research (and deep research
via the OpenAI API) looks for by name.

ChatGPT's deep-research/company-knowledge flow calls a tool literally named
``search`` (query -> list of ``{id, title, url}``) then ``fetch`` (id -> full
document as ``{id, title, text, url, metadata}``). These two are thin adapters
over the same STAC catalog the richer tools use:

- ``search`` reshapes ``search_catalog`` results into the id/title/url triples
  deep research expects.
- ``fetch`` renders ``get_dataset_info`` into a plain-text document.

They intentionally return less than ``search_catalog`` / ``get_dataset_info``;
their descriptions point rich clients (Claude, agents) at those detailed tools
and reserve this pair as the generic research interface.
"""

from __future__ import annotations

from typing import Any

from mcp.types import ToolAnnotations

from server import config
from server.app import mcp
from server.registry import register_tool
from server.tools.get_dataset_info import get_dataset_info
from server.tools.search_catalog import search_catalog

_READ_ONLY = ToolAnnotations(readOnlyHint=True, openWorldHint=True)


def _catalog_url(collection_id: str) -> str:
    return f"{config.CATALOG_PAGE_BASE_URL.rstrip('/')}/{collection_id}/"


@register_tool(mcp, title="Search datasets (deep research)", annotations=_READ_ONLY)
async def search(query: str) -> dict[str, Any]:
    """Search dynamical.org's weather & climate dataset catalog and return
    matching datasets as {id, title, url} for retrieval with `fetch`.

    This is the generic research-style entry point (the shape ChatGPT deep
    research expects). For ranked results with variables and resolution inline,
    use `search_catalog`; for a dataset's full structured fields, use
    `get_dataset_info`.

    Args:
        query: Free-text search terms, e.g. "hourly precipitation CONUS".

    Returns:
        {"results": [{"id", "title", "url"}, ...]} — pass an id to `fetch`.
    """
    found = await search_catalog(query=query, limit=10)
    results = [
        {
            "id": r["collection_id"],
            "title": r.get("title") or r.get("model_name") or r["collection_id"],
            "url": _catalog_url(r["collection_id"]),
        }
        for r in found["results"]
    ]
    return {"results": results}


def _render_document(info: dict[str, Any]) -> str:
    """Flatten a get_dataset_info payload into a readable plain-text document."""
    lines: list[str] = []
    title = info.get("title") or info.get("model_name") or info["collection_id"]
    lines.append(title)
    if info.get("description_summary"):
        lines.append("")
        lines.append(info["description_summary"])

    facts = [
        ("Model", info.get("model_name")),
        ("Spatial domain", info.get("spatial_domain")),
        ("Spatial resolution", info.get("spatial_resolution")),
        ("Time domain", info.get("time_domain")),
        ("Time resolution", info.get("time_resolution")),
        ("Forecast range", info.get("forecast_domain")),
        ("License", info.get("license")),
        ("Attribution", info.get("attribution")),
    ]
    fact_lines = [f"{label}: {value}" for label, value in facts if value]
    if fact_lines:
        lines.append("")
        lines.extend(fact_lines)

    variables = info.get("variables") or []
    if variables:
        names = ", ".join(v["name"] for v in variables)
        lines.append("")
        lines.append(f"Variables ({len(variables)}): {names}")

    if info.get("docs_url"):
        lines.append("")
        lines.append(f"Documentation: {info['docs_url']}")
    return "\n".join(lines)


@register_tool(mcp, title="Fetch dataset document (deep research)", annotations=_READ_ONLY)
async def fetch(id: str) -> dict[str, Any]:
    """Retrieve the full documentation for a dataset by id (from `search`) as a
    plain-text document plus metadata.

    For structured fields (per-variable units, bbox, example notebooks) use
    `get_dataset_info`; for a ready-to-run access snippet use
    `get_access_pattern`.

    Args:
        id: A dataset id returned by `search` (a STAC collection id, e.g.
            "noaa-gfs-forecast").

    Returns:
        {"id", "title", "text", "url", "metadata"}. Raises ValueError (listing
        valid ids) if id is unknown.
    """
    info = await get_dataset_info(collection_id=id)
    return {
        "id": id,
        "title": info.get("title") or info.get("model_name") or id,
        "text": _render_document(info),
        "url": info.get("docs_url") or _catalog_url(id),
        "metadata": {
            "model_name": info.get("model_name"),
            "spatial_resolution": info.get("spatial_resolution"),
            "time_resolution": info.get("time_resolution"),
            "forecast_domain": info.get("forecast_domain"),
            "license": info.get("license"),
            "variable_count": len(info.get("variables") or []),
        },
    }
