"""Client for dynamical.org's pipeline status feed.

status.dynamical.org itself is a "wxopticon" FastAPI app whose useful
endpoints (``/v1/catalog`` etc., discovered via its live ``/openapi.json``)
require a GitHub-login session or admin token -- that's the subscription
management API, not something a public v1 MCP server should depend on.

The status page's own "arrivals" UI doesn't call that API either: per its
``wxopticon.js`` source, it polls a public, unauthenticated static asset,
regenerated continuously, at ``STATUS_SUMMARY_URL``. That's what we use
here. Its shape (confirmed by fetching it live):

    {
      "generated_at": "<iso8601>",
      "window_days": 90,
      "sla_status": "ok",
      "products": [
        {
          "id": "noaa-gfs-forecast",       # matches dynamical STAC collection ids
          "label": "NOAA GFS forecast",
          "source": "s3://...",
          "cadence_hours": 6,
          "expected_lead_count": 1,
          "latency_stats": {"p50_s": ..., "p95_s": ..., "p99_s": ..., "avg_s": ...},
          "next_expected_init": "<iso8601>",
          "next_expected_completion_at": "<iso8601>",
          "recent_inits": [
            {
              "init_time": "<iso8601>",
              "status": "complete" | "processing",
              "completion_pct": 1.0,
              "leads_available": 1,
              "leads_expected": 1,
              "on_timedness": "on_time" | "on_track" | "late" | "unobserved",
              "completed_at": "<iso8601>" | null,
              "latency_s": 20405.0,
            },
            ...
          ],
        },
        ...
      ],
    }

Only *forecast* products are pipeline-monitored today -- product ids that
match a dynamical STAC collection id are the forecast collections
(``noaa-gfs-forecast``, ``noaa-hrrr-forecast-48-hour``, etc); the
``external-*`` ids track upstream source feeds, and analysis collections
(``noaa-gfs-analysis``, ``noaa-hrrr-analysis``, ``noaa-mrms-*``,
``noaa-gefs-analysis``) aren't in the feed at all yet.
"""

from __future__ import annotations

from typing import Any

from server import config
from server.cache import TTLCache
from server.http import get_http_client

_status_cache: TTLCache[dict[str, Any]] = TTLCache(config.STATUS_CACHE_TTL_SECONDS)


async def _fetch_summary() -> dict[str, Any]:
    client = get_http_client()
    response = await client.get(config.STATUS_SUMMARY_URL)
    response.raise_for_status()
    return response.json()


async def get_status_summary() -> dict[str, Any]:
    return await _status_cache.get_or_fetch("summary", _fetch_summary)


def find_product(summary: dict[str, Any], collection_id: str) -> dict[str, Any] | None:
    for product in summary.get("products", []):
        if product.get("id") == collection_id:
            return product
    return None


def monitored_collection_ids(summary: dict[str, Any]) -> list[str]:
    """Product ids that correspond to dynamical STAC collections, i.e.
    everything except the "external-*" upstream-source trackers."""
    return [
        pid
        for p in summary.get("products", [])
        if (pid := p.get("id")) and not pid.startswith("external-")
    ]
