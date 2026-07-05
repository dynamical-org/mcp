# dynamical.org MCP server

A remote MCP server that wraps [dynamical.org](https://dynamical.org)'s public
[STAC catalog](https://stac.dynamical.org/catalog.json) of cloud-optimized
weather and climate datasets as LLM tools: search the catalog, look up a
dataset's docs and update cadence, get a ready-to-run code snippet for
opening its data, and check forecast-run freshness.

STAC is the source of truth here — [dynamical.org/catalog](https://dynamical.org/catalog)
itself is rendered from the same catalog this server reads, and this server
fetches it live (with a short TTL cache) rather than embedding a snapshot.

## Tools

- **`search_catalog(query, limit=5)`** — search collections by model name,
  variable, region, or resolution.
- **`get_dataset_info(collection_id)`** — docs link, resolution, domain,
  update cadence, and variables for a dataset (e.g. `noaa-gfs-forecast`,
  `noaa-hrrr-analysis`, `ecmwf-aifs-ens-forecast`).
- **`get_access_pattern(collection_id)`** — the recommended
  [`dynamical-catalog`](https://pypi.org/project/dynamical-catalog/) snippet
  (dynamical.org's own wrapper package, which reads the STAC catalog itself
  to resolve storage — so it can't go stale), plus the raw asset URI/type
  and a lower-level xarray/icechunk (or zarr/GeoParquet, depending on the
  asset's declared type) snippet for direct access.
- **`list_recent_runs(collection_id, limit=10)`** — run freshness and
  arrival status from the same public feed
  [status.dynamical.org](https://status.dynamical.org)'s dashboard polls.
  Only forecast collections are pipeline-monitored today.

v1 ships with no auth — every tool above is public. v2 is planned to add
optional GitHub OAuth (a Bearer token) gating additional premium tools; see
[`server/registry.py`](server/registry.py) for how tool registration is set
up to make that additive rather than a rewrite.

## Why Python + FastMCP

This server is a thin, read-only proxy over a couple of public JSON HTTP
APIs — no need for a second language or runtime. The official
[Python MCP SDK](https://github.com/modelcontextprotocol/python-sdk)'s
`FastMCP` gives decorator-based tool registration and a built-in streamable
HTTP ASGI app (`mcp.streamable_http_app()`), which is what's needed to run
as a remote connector rather than over stdio. It also composes cleanly with
FastMCP's `auth`/`TokenVerifier` hooks for the v2 OAuth gating, and matches
the stack `dynamical-org/wxopticon` already runs (FastAPI/Starlette on
Modal), so deployment infra is consistent across the org's services.

## Local development

Requires Python 3.11+.

```bash
uv sync --group dev          # or: pip install -e '.[dev]' equivalent via pyproject
uv run python -m server      # streamable HTTP on http://0.0.0.0:8000/mcp
```

Run the tests:

```bash
uv run pytest
uv run ruff check .
```

Tests mock all upstream HTTP calls (via `respx`) against fixtures captured
from the real STAC catalog and status feed — no network access needed.

### Connecting a client

Point any MCP client that supports streamable HTTP at
`http://<host>:8000/mcp`. For a quick manual check:

```bash
uv run python -c "
import asyncio
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

async def main():
    async with streamablehttp_client('http://127.0.0.1:8000/mcp') as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print(await session.list_tools())

asyncio.run(main())
"
```

To add this server as a Claude connector, deploy it (see below) and add its
public `https://<host>/mcp` URL as a remote MCP connector.

## Deployment (Modal)

Deployment follows the same pattern as
[`dynamical-org/wxopticon`](https://github.com/dynamical-org/wxopticon)'s
`modal_app.py`: a Modal App wrapping the FastMCP ASGI app, kept warm with
`min_containers=1` so a client's `initialize` call doesn't pay a cold start.

```bash
modal deploy modal_app.py
```

v1 needs no secrets. Once a subdomain is chosen (e.g. `mcp.dynamical.org`,
matching `status.dynamical.org`'s naming), add it via `custom_domains=[...]`
on the `@modal.asgi_app()` call in `modal_app.py` and create the CNAME per
Modal's dashboard instructions — see the comments in that file.

## Configuration

Upstream URLs and cache TTLs are all overridable via environment variables
(see `server/config.py`) for pointing at a staging catalog or tuning
freshness vs. request volume; the defaults point at the production STAC
catalog and status feed.

## Repository layout

```
server/
  app.py           FastMCP instance + tool registration
  registry.py       register_tool() wrapper (auth-gating extension point)
  config.py         upstream URLs, cache TTLs
  http.py           shared httpx.AsyncClient
  cache.py          tiny async TTL cache
  stac_client.py    STAC catalog/collection fetching + parsing helpers
  status_client.py  status.dynamical.org pipeline feed client
  tools/            one module per MCP tool
tests/              pytest + respx, fixtures under tests/fixtures/
modal_app.py        Modal deployment (see above)
```
