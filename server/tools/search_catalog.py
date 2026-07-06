from __future__ import annotations

from typing import Any

from mcp.types import ToolAnnotations

from server import stac_client
from server.app import mcp
from server.registry import register_tool


@register_tool(
    mcp,
    title="Search weather & climate catalog",
    annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=True),
)
async def search_catalog(query: str, limit: int = 5) -> dict[str, Any]:
    """Search dynamical.org's STAC catalog of cloud-optimized weather and
    climate datasets.

    Matches against each dataset's model name, description, spatial/time
    domain and resolution, forecast range, and variable names -- so a query
    can be a model ("GFS"), a variable ("precipitation", "temperature_2m"),
    a region ("continental US", "global"), or a resolution ("3km", "0.25
    degree"). Results are ranked by number of matching terms.

    Args:
        query: Free-text search terms, e.g. "hourly precipitation CONUS"
            or "ECMWF ensemble forecast".
        limit: Maximum number of results to return (default 5).

    Returns:
        {"query": ..., "results": [{"collection_id", "title", "model_name",
        "description_summary", "spatial_domain", "spatial_resolution",
        "matched_variables", "score"}, ...]}, most relevant first. Pass a
        result's collection_id to get_dataset_info, get_access_pattern, or
        list_recent_runs.
    """
    query_tokens = [t for t in query.lower().split() if t]
    if not query_tokens:
        raise ValueError("query must not be empty")

    collections = await stac_client.get_all_collections()

    scored = []
    for collection_id, collection in collections.items():
        haystack = stac_client.searchable_text(collection)
        score = sum(haystack.count(token) for token in query_tokens)
        if score == 0:
            continue

        matched_variables = [
            var["name"]
            for var in stac_client.variable_summaries(collection)
            if any(
                token in f"{var['name']} {var.get('long_name') or ''}".lower()
                for token in query_tokens
            )
        ]

        summaries = collection.get("summaries", {})
        scored.append(
            {
                "collection_id": collection_id,
                "title": collection.get("title"),
                "model_name": collection.get("model_name"),
                "description_summary": collection.get("description_summary"),
                "spatial_domain": next(iter(summaries.get("spatial_domain", [])), None),
                "spatial_resolution": next(iter(summaries.get("spatial_resolution", [])), None),
                "matched_variables": matched_variables[:10],
                "score": score,
            }
        )

    scored.sort(key=lambda result: result["score"], reverse=True)
    return {"query": query, "results": scored[:limit]}
