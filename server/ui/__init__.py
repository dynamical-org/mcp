"""MCP Apps UI widgets (interactive, host-rendered HTML resources).

Each widget is a self-contained HTML file in this package, registered as an MCP
resource under a ``ui://`` URI. A tool references it via ``_meta`` (see
``server.registry.register_app_tool``); the host then renders the HTML in a
sandboxed iframe and injects the tool's structured output into it.

Two things to know about how this fits the rest of the server:

- **Dual-host.** Claude/MCP-Apps hosts match on ``text/html;profile=mcp-app``
  and the ``io.modelcontextprotocol/ui`` extension; ChatGPT/OpenAI Apps SDK
  matches on ``text/html+skybridge`` and ``openai/*`` metadata. A single
  resource carries one mimeType, so each widget is registered *twice* -- once
  per dialect -- sharing one HTML body.

- **CSP is per-resource, not per-endpoint.** The widget is rendered by the host
  from the resource body, never fetched from our ``/mcp`` endpoint, so the
  strict endpoint CSP in ``server.web`` does not govern it. The domains a widget
  needs (to frame the viewer, fetch data) are declared here in each resource's
  ``_meta`` and enforced by the host's iframe sandbox.
"""

from __future__ import annotations

from functools import cache
from importlib import resources

from mcp.server.fastmcp import FastMCP

# --- Widget resource URIs ------------------------------------------------------
# The MCP Apps and Skybridge variants of a widget share one HTML body but need
# distinct URIs so a host resolves the one matching the mimeType it supports.
DATASET_MAP_MCP = "ui://dynamical-catalog/dataset-map.html"
DATASET_MAP_SKYBRIDGE = "ui://dynamical-catalog/dataset-map.skybridge.html"

_MCP_APP_MIME = "text/html;profile=mcp-app"
_SKYBRIDGE_MIME = "text/html+skybridge"

# --- Per-resource CSP ----------------------------------------------------------
# The dataset-map widget embeds the hosted zarr-viewer in a nested iframe and,
# defensively, may talk to the data store directly. Keep this list as narrow as
# the widget actually needs.
_FRAME_DOMAINS = ["https://source-cooperative.github.io"]
_CONNECT_DOMAINS = ["https://data.source.coop"]
# OpenAI's widgetCSP has no frame-domain field; list the framed host under
# resource_domains too so ChatGPT at least allows loading it if it honors that.
_RESOURCE_DOMAINS = ["https://source-cooperative.github.io"]


@cache
def _load_html(name: str) -> str:
    """Read a widget HTML file bundled in this package (cached; files are
    static and the container is long-lived)."""
    return resources.files(__package__).joinpath(name).read_text(encoding="utf-8")


def register_widget(
    mcp: FastMCP,
    *,
    html_file: str,
    mcp_uri: str,
    skybridge_uri: str,
    description: str,
) -> None:
    """Register a widget's HTML as two resources (MCP Apps + Skybridge)."""

    def _body() -> str:
        return _load_html(html_file)

    mcp.resource(
        mcp_uri,
        name=f"{html_file} (MCP Apps)",
        description=description,
        mime_type=_MCP_APP_MIME,
        meta={
            "io.modelcontextprotocol/ui": {
                "csp": {
                    "frameDomains": _FRAME_DOMAINS,
                    "connectDomains": _CONNECT_DOMAINS,
                }
            }
        },
    )(_body)

    mcp.resource(
        skybridge_uri,
        name=f"{html_file} (Skybridge)",
        description=description,
        mime_type=_SKYBRIDGE_MIME,
        meta={
            "openai/widgetCSP": {
                "connect_domains": _CONNECT_DOMAINS,
                "resource_domains": _RESOURCE_DOMAINS,
            }
        },
    )(_body)


def register_app_resources(mcp: FastMCP) -> None:
    """Register every UI widget resource on the FastMCP instance.

    Note: capability negotiation for the ``io.modelcontextprotocol/ui``
    extension is entirely client-driven -- ``ServerCapabilities`` has no
    ``extensions`` field in mcp 1.28 and FastMCP exposes no hook to advertise
    one, so hosts detect UI purely by the ``ui://`` URI + widget mimeType + the
    tool's ``_meta``. Nothing needs to be declared server-side.
    """
    register_widget(
        mcp,
        html_file="dataset-map.html",
        mcp_uri=DATASET_MAP_MCP,
        skybridge_uri=DATASET_MAP_SKYBRIDGE,
        description=(
            "Interactive map of a dynamical.org dataset: embeds the Source "
            "Cooperative zarr-viewer for the dataset's Icechunk/Zarr store, "
            "framed in dynamical.org's branding."
        ),
    )


__all__ = [
    "DATASET_MAP_MCP",
    "DATASET_MAP_SKYBRIDGE",
    "register_app_resources",
    "register_widget",
]
