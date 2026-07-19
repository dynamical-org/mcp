"""Client for dynamical.org's public STAC catalog.

The structure of the STAC catalog this client depends on:

- The root (``STAC_ROOT_URL``) is a STAC ``Catalog`` whose only useful
  content is ``links`` with ``rel: child`` entries, one per dataset
  ``Collection``.
- Each child ``Collection`` document uses the ``xarray-assets`` and
  ``datacube`` STAC extensions. There are no STAC ``Item``s underneath --
  each collection *is* a single analysis-ready datacube (e.g. dimensioned
  by ``init_time``/``lead_time``/``latitude``/``longitude``), not a
  time series of discrete items. Relevant collection fields:
    - ``model_id`` / ``model_name``: short + human dataset identifiers.
    - ``description`` / ``description_summary`` / ``description_details`` /
      ``description_model``: prose at increasing levels of detail.
    - ``summaries``: dicts of single-element lists such as
      ``spatial_domain``, ``spatial_resolution``, ``time_domain``,
      ``time_resolution``, and (for forecasts) ``forecast_domain`` /
      ``forecast_resolution``.
    - ``cube:dimensions`` / ``cube:variables``: the datacube extension's
      dimension and variable metadata (units, long/short names, chunking).
    - ``dynamical-org:chunking``: chunk/shard layout, dtype.
    - ``assets``: currently always a single ``icechunk`` asset
      (``type: application/x-icechunk``) with an ``s3://`` href and
      ``xarray:open_kwargs`` / ``xarray:storage_options`` for opening it.
      Written generically below (keyed off ``type``/href suffix) since a
      future collection could publish a plain ``zarr`` or GeoParquet asset
      instead.
    - ``links``: ``rel: about`` points at the human-readable docs page on
      dynamical.org/catalog/<id>/; ``rel: example`` links point at
      quickstart notebooks.
"""

from __future__ import annotations

import asyncio
from typing import Any

from server import config
from server.cache import TTLCache
from server.errors import ToolInputError
from server.http import get_http_client

_catalog_cache: TTLCache[dict[str, Any]] = TTLCache(config.STAC_CACHE_TTL_SECONDS)
_collection_cache: TTLCache[dict[str, Any]] = TTLCache(config.STAC_CACHE_TTL_SECONDS)


class CollectionNotFoundError(ToolInputError):
    def __init__(self, collection_id: str, known_ids: list[str]):
        self.collection_id = collection_id
        self.known_ids = known_ids
        super().__init__(
            f"Unknown collection_id {collection_id!r}. Known collection ids: "
            f"{', '.join(sorted(known_ids))}"
        )


async def _fetch_json(url: str) -> dict[str, Any]:
    client = get_http_client()
    response = await client.get(url)
    response.raise_for_status()
    return response.json()


async def get_catalog() -> dict[str, Any]:
    """Return the raw STAC root Catalog document (cached)."""
    return await _catalog_cache.get_or_fetch(
        config.STAC_ROOT_URL, lambda: _fetch_json(config.STAC_ROOT_URL)
    )


def _child_links(catalog: dict[str, Any]) -> list[dict[str, Any]]:
    return [link for link in catalog.get("links", []) if link.get("rel") == "child"]


async def list_collection_refs() -> list[dict[str, str]]:
    """Return [{id, title, href}] for every collection in the catalog, without
    fetching each collection document."""
    catalog = await get_catalog()
    refs = []
    for link in _child_links(catalog):
        href = link["href"]
        # Collection ids are the path segment before /collection.json, and
        # match the STAC Collection's own "id" field.
        collection_id = href.rstrip("/").split("/")[-2]
        refs.append({"id": collection_id, "title": link.get("title", collection_id), "href": href})
    return refs


async def get_collection(collection_id: str) -> dict[str, Any]:
    """Fetch (and cache) a single collection.json by id."""
    refs = await list_collection_refs()
    ref_by_id = {ref["id"]: ref for ref in refs}
    ref = ref_by_id.get(collection_id)
    if ref is None:
        raise CollectionNotFoundError(collection_id, list(ref_by_id.keys()))
    return await _collection_cache.get_or_fetch(collection_id, lambda: _fetch_json(ref["href"]))


async def get_all_collections() -> dict[str, dict[str, Any]]:
    """Fetch (and cache) every collection document, concurrently."""
    refs = await list_collection_refs()
    collections = await asyncio.gather(*(get_collection(ref["id"]) for ref in refs))
    return {c["id"]: c for c in collections}


def get_link(collection: dict[str, Any], rel: str) -> dict[str, Any] | None:
    for link in collection.get("links", []):
        if link.get("rel") == rel:
            return link
    return None


def get_links(collection: dict[str, Any], rel: str) -> list[dict[str, Any]]:
    return [link for link in collection.get("links", []) if link.get("rel") == rel]


def data_asset(collection: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Return (asset_key, asset) for the primary data asset of a collection."""
    assets = collection.get("assets", {})
    for key, asset in assets.items():
        if "data" in asset.get("roles", []):
            return key, asset
    if assets:
        # Fall back to the only/first asset if none is explicitly tagged "data".
        key = next(iter(assets))
        return key, assets[key]
    raise ValueError(f"Collection {collection.get('id')!r} has no assets")


def variable_summaries(collection: dict[str, Any]) -> list[dict[str, Any]]:
    variables = collection.get("cube:variables", {})
    return [
        {
            "name": name,
            "short_name": var.get("short_name"),
            "long_name": var.get("long_name"),
            "unit": var.get("unit"),
            "dimensions": var.get("dimensions"),
        }
        for name, var in variables.items()
        if var.get("type", "data") == "data"
    ]


def searchable_text(collection: dict[str, Any]) -> str:
    """Flatten the fields worth full-text matching in search_catalog into one
    lowercase string: id/title/model name, prose, domain/resolution
    summaries, and variable names."""
    parts: list[str] = [
        collection.get("id", ""),
        collection.get("title", ""),
        collection.get("model_id", ""),
        collection.get("model_name", ""),
        collection.get("description", ""),
        collection.get("description_summary", ""),
        collection.get("description_model", ""),
    ]
    for values in collection.get("summaries", {}).values():
        parts.extend(str(v) for v in values)
    for var in variable_summaries(collection):
        parts.append(var["name"])
        parts.append(var.get("short_name") or "")
        parts.append(var.get("long_name") or "")
    return " ".join(parts).lower()
