from __future__ import annotations

from typing import Any

from mcp.types import ToolAnnotations

from server import stac_client
from server.app import mcp
from server.registry import register_app_tool
from server.ui import DATASET_MAP_MCP, DATASET_MAP_SKYBRIDGE


def _first(summaries: dict, key: str) -> str | None:
    return next(iter(summaries.get(key, [])), None)


@register_app_tool(
    mcp,
    ui_resource_uri=DATASET_MAP_MCP,
    openai_output_template=DATASET_MAP_SKYBRIDGE,
    title="Get dataset details",
    annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=True),
)
async def get_dataset_info(collection_id: str) -> dict[str, Any]:
    """Get documentation, spatial/time resolution, domain, and update cadence
    for one dynamical.org dataset.

    dynamical.org/catalog is itself rendered from this same STAC catalog, so
    this tool fetches the collection document live (short TTL cache) rather
    than relying on anything baked into this server -- it's always as fresh
    as the STAC catalog itself.

    Args:
        collection_id: A STAC collection id, e.g. "noaa-gfs-forecast",
            "noaa-hrrr-analysis", or "ecmwf-aifs-ens-forecast". Use
            search_catalog to discover ids.

    Returns:
        A dict with title/model name, prose descriptions, spatial and time
        domain/resolution, forecast range (for forecast datasets), license
        and attribution, the dataset's variables, links to its docs page and
        example notebooks, and the dataset's browser-openable data store URL
        plus a deep-link into the hosted zarr-viewer (which also backs the
        interactive map widget this tool renders). Raises ValueError (listing
        valid ids) if collection_id is unknown.
    """
    collection = await stac_client.get_collection(collection_id)
    summaries = collection.get("summaries", {})
    extent = collection.get("extent", {})

    docs_link = stac_client.get_link(collection, "about")
    example_links = stac_client.get_links(collection, "example")
    self_link = stac_client.get_link(collection, "self")

    return {
        "collection_id": collection["id"],
        "title": collection.get("title"),
        "model_id": collection.get("model_id"),
        "model_name": collection.get("model_name"),
        "description": collection.get("description"),
        "description_summary": collection.get("description_summary"),
        "description_model": collection.get("description_model"),
        "attribution": collection.get("attribution"),
        "license": collection.get("license"),
        "version": collection.get("version"),
        "spatial_domain": _first(summaries, "spatial_domain"),
        "spatial_resolution": _first(summaries, "spatial_resolution"),
        "time_domain": _first(summaries, "time_domain"),
        "time_resolution": _first(summaries, "time_resolution"),
        "forecast_domain": _first(summaries, "forecast_domain"),
        "forecast_resolution": _first(summaries, "forecast_resolution"),
        "spatial_bbox": next(iter(extent.get("spatial", {}).get("bbox", [])), None),
        "temporal_interval": next(iter(extent.get("temporal", {}).get("interval", [])), None),
        "variables": stac_client.variable_summaries(collection),
        "docs_url": docs_link["href"] if docs_link else None,
        "example_notebooks": [
            {"title": link.get("title"), "url": link["href"]} for link in example_links
        ],
        # Prefer the collection's own `self` link so this stays correct if the
        # catalog is served from a different host (e.g. staging via config).
        "stac_collection_url": self_link["href"] if self_link else None,
        # Browser-openable data store (https, derived from the s3:// asset) and
        # a ready deep-link into the hosted zarr-viewer. The map widget renders
        # from data_viewer_url; both are None if no store URL can be derived.
        "data_store_url": stac_client.source_coop_https_url(collection),
        "data_viewer_url": stac_client.zarr_viewer_url(collection),
    }
