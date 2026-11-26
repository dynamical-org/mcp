"""Central place for the upstream URLs and cache TTLs this server depends on."""

from __future__ import annotations

import os

STAC_ROOT_URL = os.environ.get("DYNAMICAL_STAC_ROOT_URL", "https://stac.dynamical.org/catalog.json")
CATALOG_PAGE_BASE_URL = os.environ.get(
    "DYNAMICAL_CATALOG_PAGE_BASE_URL", "https://dynamical.org/catalog"
)
STATUS_SUMMARY_URL = os.environ.get(
    "DYNAMICAL_STATUS_SUMMARY_URL", "https://assets.dynamical.org/wxopticon/summary.json"
)

# STAC documents change on dataset releases (infrequent); poll modestly.
STAC_CACHE_TTL_SECONDS = float(os.environ.get("DYNAMICAL_STAC_CACHE_TTL_SECONDS", 900))
# The pipeline status feed is regenerated roughly every 15s upstream, but
# per-run freshness at minute granularity is plenty for an LLM tool call.
STATUS_CACHE_TTL_SECONDS = float(os.environ.get("DYNAMICAL_STATUS_CACHE_TTL_SECONDS", 120))
# Docs pages / notebooks change rarely; cache a bit longer than STAC.
DOCS_CACHE_TTL_SECONDS = float(os.environ.get("DYNAMICAL_DOCS_CACHE_TTL_SECONDS", 1800))

HTTP_TIMEOUT_SECONDS = float(os.environ.get("DYNAMICAL_HTTP_TIMEOUT_SECONDS", 15))
USER_AGENT = "dynamical-mcp-server/0.1 (+https://github.com/dynamical-org/mcp)"
