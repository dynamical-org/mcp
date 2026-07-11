"""Tests for the MCP Apps UI widget wiring (resources + tool linkage)."""

from server.app import mcp
from server.ui import DATASET_MAP_MCP, DATASET_MAP_SKYBRIDGE


async def test_get_dataset_info_links_the_map_widget():
    tools = {t.name: t for t in await mcp.list_tools()}
    meta = tools["get_dataset_info"].meta
    assert meta is not None
    assert meta["ui"]["resourceUri"] == DATASET_MAP_MCP
    assert meta["io.modelcontextprotocol/ui"]["resourceUri"] == DATASET_MAP_MCP
    assert meta["openai/outputTemplate"] == DATASET_MAP_SKYBRIDGE


async def test_widget_registered_for_both_host_dialects():
    resources = {str(r.uri): r for r in await mcp.list_resources()}
    assert DATASET_MAP_MCP in resources
    assert DATASET_MAP_SKYBRIDGE in resources

    mcp_res = resources[DATASET_MAP_MCP]
    assert mcp_res.mimeType == "text/html;profile=mcp-app"
    csp = mcp_res.meta["io.modelcontextprotocol/ui"]["csp"]
    assert "https://source-cooperative.github.io" in csp["frameDomains"]
    assert "https://data.source.coop" in csp["connectDomains"]

    sky_res = resources[DATASET_MAP_SKYBRIDGE]
    assert sky_res.mimeType == "text/html+skybridge"
    widget_csp = sky_res.meta["openai/widgetCSP"]
    assert "https://data.source.coop" in widget_csp["connect_domains"]
    assert "https://source-cooperative.github.io" in widget_csp["resource_domains"]


async def test_widget_resource_body_is_html():
    for uri in (DATASET_MAP_MCP, DATASET_MAP_SKYBRIDGE):
        contents = await mcp.read_resource(uri)
        assert contents, uri
        body = contents[0]
        assert body.content
        assert "<html" in body.content.lower()
        # Same HTML body backs both dialects.
        assert "zarr-viewer" in body.content


async def test_tool_count_unchanged():
    """Adding the widget attaches meta to an existing tool -- it must not add a
    new tool to the advertised set."""
    names = {t.name for t in await mcp.list_tools()}
    assert names == {
        "search_catalog",
        "get_dataset_info",
        "get_access_pattern",
        "list_recent_runs",
    }
