from server import status_client


async def test_find_product_match(mock_status):
    summary = await status_client.get_status_summary()
    product = status_client.find_product(summary, "noaa-gfs-forecast")
    assert product is not None
    assert product["cadence_hours"] == 6


async def test_find_product_no_match(mock_status):
    summary = await status_client.get_status_summary()
    assert status_client.find_product(summary, "not-a-product") is None


async def test_monitored_collection_ids_excludes_external(mock_status):
    summary = await status_client.get_status_summary()
    ids = status_client.monitored_collection_ids(summary)
    assert ids == ["noaa-gfs-forecast"]
