"""The shared FastMCP server instance.

Transport is streamable HTTP (not stdio) so this can be deployed and added
to Claude as a remote connector. `stateless_http=True` because every tool
here is a read-only proxy over public HTTP APIs with no session state of
its own, which makes the server trivially horizontally scalable.
"""

from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    name="dynamical-catalog",
    instructions=(
        "Tools for discovering and using dynamical.org's public STAC catalog of "
        "cloud-optimized weather and climate datasets: search for datasets by "
        "model/variable/region/resolution, look up a dataset's docs and update "
        "cadence, get a ready-to-run code snippet for opening its data, and check "
        "recent forecast-run freshness."
    ),
    host=os.environ.get("HOST", "0.0.0.0"),
    port=int(os.environ.get("PORT", 8000)),
    stateless_http=True,
)

# Importing tool modules registers them on `mcp` via `register_tool`.
from server.tools import (  # noqa: E402,F401  (import for registration side effects)
    get_access_pattern,
    get_dataset_info,
    list_recent_runs,
    search_catalog,
)
