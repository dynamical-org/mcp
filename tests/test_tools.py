import pytest

from server.app import mcp
from server.stac_client import CollectionNotFoundError
from server.tools.get_access_pattern import get_access_pattern
from server.tools.get_dataset_info import get_dataset_info
from server.tools.list_recent_runs import list_recent_runs
from server.tools.search_catalog import search_catalog


async def test_search_catalog_matches_variable_and_model(mock_stac):
    result = await search_catalog(query="temperature_2m")
    ids = [r["collection_id"] for r in result["results"]]
    assert "noaa-gfs-forecast" in ids
    assert "noaa-gfs-analysis" in ids


async def test_search_catalog_ranks_by_score(mock_stac):
    result = await search_catalog(query="forecast global")
    assert result["results"]
    assert result["results"][0]["collection_id"] == "noaa-gfs-forecast"


async def test_search_catalog_empty_query_raises(mock_stac):
    with pytest.raises(ValueError):
        await search_catalog(query="   ")


async def test_search_catalog_respects_limit(mock_stac):
    result = await search_catalog(query="noaa gfs", limit=1)
    assert len(result["results"]) == 1


async def test_get_dataset_info_forecast_fields(mock_stac):
    info = await get_dataset_info(collection_id="noaa-gfs-forecast")
    assert info["model_name"] == "NOAA GFS"
    assert info["spatial_resolution"] == "0.25 degrees (~20km)"
    assert info["forecast_domain"] == "Forecast lead time 0-384 hours (0-16 days) ahead"
    assert info["docs_url"] == "https://dynamical.org/catalog/noaa-gfs-forecast/"
    assert info["example_notebooks"][0]["url"].endswith("noaa-gfs-forecast.ipynb")


async def test_get_dataset_info_analysis_has_no_forecast_fields(mock_stac):
    info = await get_dataset_info(collection_id="noaa-gfs-analysis")
    assert info["forecast_domain"] is None
    assert info["forecast_resolution"] is None


async def test_get_dataset_info_unknown_id(mock_stac):
    with pytest.raises(CollectionNotFoundError):
        await get_dataset_info(collection_id="does-not-exist")


async def test_get_access_pattern_recommends_dynamical_catalog(mock_stac):
    pattern = await get_access_pattern(collection_id="noaa-gfs-forecast")
    assert pattern["recommended"]["package"] == "dynamical-catalog"
    assert 'dynamical_catalog.open("noaa-gfs-forecast")' in pattern["recommended"]["code"]


async def test_get_access_pattern_low_level_icechunk_snippet(mock_stac):
    pattern = await get_access_pattern(collection_id="noaa-gfs-forecast")
    low_level = pattern["low_level"]
    assert low_level["format"] == "icechunk"
    assert "icechunk.s3_storage" in low_level["code"]
    assert "bucket='dynamical-noaa-gfs'" in low_level["code"]
    assert "prefix='noaa-gfs-forecast/v0.2.7.icechunk'" in low_level["code"]


async def test_get_access_pattern_surfaces_worked_example(mock_stac):
    pattern = await get_access_pattern(collection_id="noaa-gfs-forecast")
    assert pattern["worked_example"]["title"] == "Maximum temperature in a forecast"


async def test_list_recent_runs_monitored(mock_status):
    result = await list_recent_runs(collection_id="noaa-gfs-forecast", limit=2)
    assert result["monitored"] is True
    assert result["sla_status"] == "ok"
    assert len(result["recent_runs"]) == 2
    # Most recent first.
    assert result["recent_runs"][0]["init_time"] == "2026-07-05T12:00:00+00:00"


async def test_list_recent_runs_unmonitored(mock_status):
    result = await list_recent_runs(collection_id="noaa-gfs-analysis")
    assert result["monitored"] is False
    assert "noaa-gfs-forecast" in result["monitored_collection_ids"]


async def test_all_tools_advertise_output_schema():
    """Every tool returns `dict[str, Any]`, so FastMCP should advertise an
    outputSchema for each -- clients that prefer structured output get one."""
    tools = {tool.name: tool for tool in await mcp.list_tools()}
    assert set(tools) == {
        "search_catalog",
        "get_dataset_info",
        "get_access_pattern",
        "list_recent_runs",
    }
    for tool in tools.values():
        assert tool.outputSchema is not None, tool.name


async def test_call_tool_populates_structured_content(mock_stac):
    """A tool call over the MCP layer returns both unstructured text and
    structured content (the dict itself, unwrapped)."""
    unstructured, structured = await mcp.call_tool(
        "get_dataset_info", {"collection_id": "noaa-gfs-forecast"}
    )
    assert unstructured  # text content still present for back-compat
    assert structured["collection_id"] == "noaa-gfs-forecast"
    assert structured["model_name"] == "NOAA GFS"
