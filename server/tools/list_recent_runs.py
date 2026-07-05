from __future__ import annotations

from server import status_client
from server.app import mcp
from server.registry import register_tool


@register_tool(mcp)
async def list_recent_runs(collection_id: str, limit: int = 10) -> dict:
    """Check run freshness and arrival status for a dynamical.org forecast
    dataset, from the same public feed status.dynamical.org's dashboard polls.

    Only forecast collections are pipeline-monitored today (analysis
    collections like noaa-gfs-analysis or noaa-mrms-conus-analysis-hourly
    aren't yet tracked by this feed).

    Args:
        collection_id: A STAC collection id, e.g. "noaa-gfs-forecast".
        limit: Maximum number of recent runs to return, most recent first
            (default 10).

    Returns:
        A dict with the overall pipeline `sla_status`, this product's
        cadence and next expected init/completion time, typical latency
        stats, and up to `limit` recent runs (`init_time`, `status`,
        `completion_pct`, `on_timedness`, arrival/latency timestamps). If
        collection_id isn't pipeline-monitored, returns `monitored`: False
        plus the list of collection ids that are.
    """
    summary = await status_client.get_status_summary()
    product = status_client.find_product(summary, collection_id)

    if product is None:
        return {
            "collection_id": collection_id,
            "monitored": False,
            "message": (
                f"{collection_id!r} is not pipeline-monitored (only forecast "
                "collections are, today)."
            ),
            "monitored_collection_ids": sorted(status_client.monitored_collection_ids(summary)),
        }

    recent_inits = list(reversed(product.get("recent_inits", [])))[:limit]

    return {
        "collection_id": collection_id,
        "monitored": True,
        "generated_at": summary.get("generated_at"),
        "sla_status": summary.get("sla_status"),
        "cadence_hours": product.get("cadence_hours"),
        "next_expected_init": product.get("next_expected_init"),
        "next_expected_completion_at": product.get("next_expected_completion_at"),
        "latency_stats": product.get("latency_stats"),
        "recent_runs": recent_inits,
    }
