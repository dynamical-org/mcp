"""Tool-registration wrapper.

v1 has no auth at all -- every tool registered through `register_tool` is
public. v2 is planned to add optional GitHub OAuth (a Bearer token,
verified via a `TokenVerifier` passed to `FastMCP(auth=...)`) gating a
subset of *additional* premium tools, while `search_catalog`,
`get_dataset_info`, `get_access_pattern`, and `list_recent_runs` stay open.

`requires_auth` exists now so that day's change is additive: flip the flag
on a new tool's registration and check `mcp.get_context().request_context`
for the verified identity inside it. Nothing about this v1 file needs to
change.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

from mcp.server.fastmcp import FastMCP

F = TypeVar("F", bound=Callable[..., Any])


def register_tool(
    mcp: FastMCP, *, requires_auth: bool = False, **tool_kwargs: Any
) -> Callable[[F], F]:
    if requires_auth:
        # No auth provider is wired into the FastMCP instance yet in v1.
        raise NotImplementedError(
            "requires_auth=True tools need a v2 GitHub OAuth token verifier "
            "configured on the FastMCP instance before they can be registered."
        )

    def decorator(fn: F) -> F:
        fn.__mcp_requires_auth__ = requires_auth  # type: ignore[attr-defined]
        return mcp.tool(**tool_kwargs)(fn)

    return decorator
