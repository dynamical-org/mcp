#!/usr/bin/env python3
"""Modal cron — semantic health probe for the deployed dynamical.org MCP server.

Every 10 minutes this performs a real MCP round trip against the public
streamable-HTTP endpoint (`initialize`, then `tools/list`) and asserts the
server advertises at least one tool. This replaces the Better Stack "keyword"
monitor that asserted response-body content — something Sentry Uptime
(status-code only) can't do — with a check that the MCP protocol handshake and
tool registry actually work end to end, not merely that the ASGI app answers.

A successful round trip sends an `ok` Sentry cron check-in; any failure (or a
hung request) skips it, so Sentry records a missed check-in and opens an
incident. No check-in is sent at the start of a run, so a hang surfaces as a
missed check-in rather than a stuck `in_progress` one. The monitor lives in the
`mcp` Sentry project, so its alerts route with this app's Slack channel.

Deploy (manual — this repo has no deploy CI):
    modal deploy probe.py

The DSN default is hardcoded below (matching server/obs.py's convention for
this private repo); set SENTRY_DSN to override without a code change. The MCP
endpoint is public and unauthenticated, so no credentials are needed.
"""

from __future__ import annotations

import os
from collections.abc import Sequence

import modal

MCP_URL = "https://mcp.dynamical.org/mcp"

# Hardcoded default (private repo), overridable via env — same convention as
# server/obs.py. This is the `mcp` Sentry project's DSN.
SENTRY_DSN = os.environ.get(
    "SENTRY_DSN",
    "https://585916969d49a68c1ca79671abd06e3e@o4508761427804160.ingest.us.sentry.io/4511790929739776",
)

image = modal.Image.debian_slim(python_version="3.12").pip_install(
    "mcp>=1.28.0",
    "sentry-sdk>=2.20",
)

app = modal.App("mcp-probe")


def check_mcp_tools(tool_names: Sequence[str]) -> int:
    """Assert the MCP server advertised at least one tool; return the tool count."""
    assert tool_names, "MCP tools/list returned no tools"
    return len(tool_names)


@app.function(
    image=image,
    schedule=modal.Period(minutes=10),
    timeout=120,
)
def mcp_probe() -> None:
    import asyncio

    import sentry_sdk
    import sentry_sdk.crons
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    # No-op when the DSN is unset (e.g. overridden to empty for a dry run).
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        environment=os.environ.get("SENTRY_ENVIRONMENT", "production"),
        enable_logs=True,
    )
    monitor_config = {
        # Must match the `modal.Period` schedule above.
        "schedule": {"type": "interval", "value": 10, "unit": "minute"},
        "timezone": "UTC",
        "checkin_margin": 5,
        "failure_issue_threshold": 1,
        "recovery_threshold": 1,
    }

    async def roundtrip() -> list[str]:
        async with (
            streamablehttp_client(MCP_URL) as (read, write, _),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            result = await session.list_tools()
            return [tool.name for tool in result.tools]

    # No check-in is sent at the start of the run, so a hang produces a missed
    # check-in instead of a stuck `in_progress` one.
    try:
        check_mcp_tools(asyncio.run(roundtrip()))
    except Exception:
        sentry_sdk.capture_exception()
        sentry_sdk.crons.capture_checkin(
            monitor_slug="mcp-probe", status="error", monitor_config=monitor_config
        )
        raise
    sentry_sdk.crons.capture_checkin(
        monitor_slug="mcp-probe", status="ok", monitor_config=monitor_config
    )
