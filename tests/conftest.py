import json
from pathlib import Path

import pytest
import respx
from httpx import Response

from server import stac_client, status_client

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture(autouse=True)
def _reset_caches():
    """Every cache is keyed by upstream URL; clear between tests so mocked
    responses from one test can't leak into the next."""
    stac_client._catalog_cache.invalidate()
    stac_client._collection_cache.invalidate()
    status_client._status_cache.invalidate()
    yield


@pytest.fixture
def mock_stac():
    with respx.mock(assert_all_called=False) as router:
        router.get("https://stac.dynamical.org/catalog.json").mock(
            return_value=Response(200, json=_load("catalog.json"))
        )
        router.get("https://stac.dynamical.org/noaa-gfs-forecast/collection.json").mock(
            return_value=Response(200, json=_load("collection_forecast.json"))
        )
        router.get("https://stac.dynamical.org/noaa-gfs-analysis/collection.json").mock(
            return_value=Response(200, json=_load("collection_analysis.json"))
        )
        yield router


@pytest.fixture
def mock_status():
    with respx.mock(assert_all_called=False) as router:
        router.get("https://assets.dynamical.org/wxopticon/summary.json").mock(
            return_value=Response(200, json=_load("summary.json"))
        )
        yield router
