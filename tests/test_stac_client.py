import pytest

from server import stac_client


async def test_list_collection_refs(mock_stac):
    refs = await stac_client.list_collection_refs()
    assert {r["id"] for r in refs} == {"noaa-gfs-forecast", "noaa-gfs-analysis"}


async def test_get_collection(mock_stac):
    collection = await stac_client.get_collection("noaa-gfs-forecast")
    assert collection["model_name"] == "NOAA GFS"


async def test_get_collection_unknown_id_lists_known_ids(mock_stac):
    with pytest.raises(stac_client.CollectionNotFoundError) as exc_info:
        await stac_client.get_collection("not-a-real-id")
    assert "noaa-gfs-forecast" in str(exc_info.value)
    assert "noaa-gfs-analysis" in str(exc_info.value)


async def test_get_all_collections(mock_stac):
    collections = await stac_client.get_all_collections()
    assert set(collections) == {"noaa-gfs-forecast", "noaa-gfs-analysis"}


async def test_data_asset_picks_role(mock_stac):
    collection = await stac_client.get_collection("noaa-gfs-forecast")
    key, asset = stac_client.data_asset(collection)
    assert key == "icechunk"
    assert asset["type"] == "application/x-icechunk"


async def test_variable_summaries(mock_stac):
    collection = await stac_client.get_collection("noaa-gfs-forecast")
    variables = {v["name"] for v in stac_client.variable_summaries(collection)}
    assert variables == {"temperature_2m", "precipitation_surface"}


async def test_searchable_text_includes_variables_and_domain(mock_stac):
    collection = await stac_client.get_collection("noaa-gfs-forecast")
    text = stac_client.searchable_text(collection)
    assert "temperature_2m" in text
    assert "global" in text
    assert "noaa gfs" in text
