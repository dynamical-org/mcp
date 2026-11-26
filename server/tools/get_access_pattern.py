from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from mcp.types import ToolAnnotations

from server import stac_client
from server.app import mcp
from server.registry import register_tool


def _icechunk_snippet(collection_id: str, uri: str, storage_options: dict) -> str:
    parsed = urlparse(uri)
    region = (storage_options.get("client_kwargs") or {}).get("region_name", "us-west-2")
    anonymous = bool(storage_options.get("anon", True))
    prefix = parsed.path.strip("/")
    return (
        "import icechunk\n"
        "import xarray as xr\n"
        "\n"
        "storage = icechunk.s3_storage(\n"
        f"    bucket={parsed.netloc!r},\n"
        f"    prefix={prefix!r},\n"
        f"    region={region!r},\n"
        f"    anonymous={anonymous!r},\n"
        ")\n"
        "repo = icechunk.Repository.open(storage)\n"
        'session = repo.readonly_session("main")\n'
        f"ds = xr.open_zarr(session.store, consolidated=False)  # {collection_id}\n"
    )


def _zarr_snippet(collection_id: str, uri: str, storage_options: dict) -> str:
    return (
        "import fsspec\n"
        "import xarray as xr\n"
        "\n"
        f"store = fsspec.get_mapper({uri!r}, **{storage_options!r})\n"
        f"ds = xr.open_zarr(store, consolidated=False)  # {collection_id}\n"
    )


def _geoparquet_snippet(collection_id: str, uri: str, storage_options: dict) -> str:
    return (
        "import geopandas as gpd\n"
        "\n"
        f"gdf = gpd.read_parquet({uri!r}, storage_options={storage_options!r})  # {collection_id}\n"
    )


def _low_level_snippet(
    collection_id: str, asset_type: str, uri: str, storage_options: dict
) -> dict:
    if "icechunk" in asset_type:
        kind, code = "icechunk", _icechunk_snippet(collection_id, uri, storage_options)
    elif "parquet" in asset_type or uri.endswith(".parquet"):
        kind, code = "geoparquet", _geoparquet_snippet(collection_id, uri, storage_options)
    elif "zarr" in asset_type or uri.endswith(".zarr") or uri.endswith(".zarr/"):
        kind, code = "zarr", _zarr_snippet(collection_id, uri, storage_options)
    else:
        # Unrecognized asset type: fall back to the generic zarr/fsspec pattern
        # (most dynamical.org assets are Zarr-family stores) but flag it so
        # callers know this wasn't derived from a known asset "type".
        kind, code = "unknown", _zarr_snippet(collection_id, uri, storage_options)
    return {"format": kind, "code": code}


@register_tool(
    mcp,
    title="Get data access snippet",
    annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=True),
)
async def get_access_pattern(collection_id: str) -> dict[str, Any]:
    """Get the storage URI and working code for opening a dynamical.org
    dataset's data.

    dynamical.org publishes a Python package, `dynamical-catalog`, that
    reads the STAC catalog itself to resolve and open a dataset -- it's the
    recommended access pattern because it can't go stale even if the
    underlying storage format or location changes. This tool also returns
    the dataset's low-level storage details (from the STAC asset, fetched
    live) and a lower-level xarray/fsspec snippet for callers who need
    direct access instead of the wrapper package.

    Args:
        collection_id: A STAC collection id, e.g. "noaa-gfs-forecast". Use
            search_catalog to discover ids.

    Returns:
        A dict with the recommended `dynamical_catalog.open(...)` snippet,
        a `worked_example` pulled from the collection's own STAC metadata
        when one is published, the raw asset URI/type/storage options, and
        a generated low-level open snippet (icechunk/zarr/geoparquet,
        chosen from the asset's declared type). Raises ValueError (listing
        valid ids) if collection_id is unknown.
    """
    collection = await stac_client.get_collection(collection_id)
    asset_key, asset = stac_client.data_asset(collection)
    uri = asset["href"]
    asset_type = asset.get("type", "")
    storage_options = asset.get("xarray:storage_options", {})

    examples = collection.get("examples") or []
    worked_example = examples[0] if examples else None

    return {
        "collection_id": collection_id,
        "recommended": {
            "package": "dynamical-catalog",
            "install": "pip install dynamical-catalog",
            "code": (
                f'import dynamical_catalog\n\nds = dynamical_catalog.open("{collection_id}")\n'
            ),
        },
        "worked_example": worked_example,
        "asset": {
            "key": asset_key,
            "type": asset_type,
            "uri": uri,
            "xarray_open_kwargs": asset.get("xarray:open_kwargs", {}),
            "xarray_storage_options": storage_options,
        },
        "low_level": _low_level_snippet(collection_id, asset_type, uri, storage_options),
    }
