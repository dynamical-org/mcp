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


async def test_source_coop_https_url_drops_bucket(mock_stac):
    collection = await stac_client.get_collection("noaa-gfs-forecast")
    # Asset href is s3://dynamical-noaa-gfs/noaa-gfs-forecast/v0.2.7.icechunk/;
    # the per-model bucket is dropped for the single `dynamical` source.coop
    # account, and the trailing slash is stripped.
    assert (
        stac_client.source_coop_https_url(collection)
        == "https://data.source.coop/dynamical/noaa-gfs-forecast/v0.2.7.icechunk"
    )


async def test_source_coop_https_url_none_for_non_s3():
    collection = {"assets": {"data": {"href": "https://example.com/x.zarr", "roles": ["data"]}}}
    assert stac_client.source_coop_https_url(collection) is None


async def test_source_coop_https_url_none_without_asset():
    assert stac_client.source_coop_https_url({"assets": {}}) is None


async def test_zarr_viewer_url_centres_on_bbox(mock_stac):
    collection = await stac_client.get_collection("noaa-gfs-forecast")
    url = stac_client.zarr_viewer_url(collection)
    assert url is not None
    assert url.startswith("https://source-cooperative.github.io/zarr-viewer/?")
    # Store URL is URL-encoded into the `url` param.
    assert "url=https%3A%2F%2Fdata.source.coop%2Fdynamical%2Fnoaa-gfs-forecast" in url
    assert "&panel=open" in url
    assert "lng=" in url and "lat=" in url and "zoom=" in url


async def test_zarr_viewer_url_matches_reference_for_icon_eu():
    """The derived deep-link matches the known-good reference URL for the DWD
    ICON-EU store (store URL + zoom), grounding the s3->https + camera math."""
    collection = {
        "assets": {
            "icechunk": {
                "href": "s3://dynamical-dwd-icon-eu/dwd-icon-eu-forecast-5-day/v0.2.0.icechunk/",
                "type": "application/x-icechunk",
                "roles": ["data"],
            }
        },
        "extent": {"spatial": {"bbox": [[-23.5, 29.5, 62.5, 70.5]]}},
    }
    url = stac_client.zarr_viewer_url(collection)
    assert (
        "url=https%3A%2F%2Fdata.source.coop%2Fdynamical%2F"
        "dwd-icon-eu-forecast-5-day%2Fv0.2.0.icechunk" in url
    )
    assert "&zoom=4" in url


async def test_zarr_viewer_url_none_without_store():
    assert stac_client.zarr_viewer_url({"assets": {}}) is None
