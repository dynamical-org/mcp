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

import functools
from collections.abc import Callable
from typing import Any, TypeVar

import sentry_sdk
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

        # The MCP SDK catches every tool exception and returns it to the client
        # as a JSON-RPC `isError` result over HTTP 200 (see mcp.server.lowlevel
        # `_make_error_result`). Because nothing propagates as an unhandled
        # request error, Sentry's Starlette integration never fires and tool
        # failures are invisible to Better Stack. Capture them explicitly here,
        # then re-raise unchanged so the SDK still builds the client's error
        # result. `capture_exception` is a no-op when Sentry isn't initialised
        # (local dev / tests), so this stays inert outside the deployed app.
        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return await fn(*args, **kwargs)
            except Exception:
                sentry_sdk.capture_exception()
                raise

        return mcp.tool(**tool_kwargs)(wrapper)  # type: ignore[return-value]

    return decorator


def register_app_tool(
    mcp: FastMCP,
    *,
    ui_resource_uri: str,
    openai_output_template: str | None = None,
    ui_visibility: list[str] | None = None,
    meta: dict[str, Any] | None = None,
    **tool_kwargs: Any,
) -> Callable[[F], F]:
    """Register a tool that renders an MCP Apps UI widget.

    Layers the UI linkage on top of `register_tool` without changing it. The
    widget is a `ui://` HTML resource (see `server.ui`); this attaches the
    per-host `_meta` that points a host at that resource:

    - `ui` / `io.modelcontextprotocol/ui` -- the MCP Apps extension (SEP-1865).
      Both the short `ui` key and the fully-qualified extension key are emitted
      so we're robust to the key shape the host actually matches on while the
      spec settles.
    - `openai/outputTemplate` -- the OpenAI Apps SDK (ChatGPT) equivalent,
      pointing at the Skybridge variant of the same widget.

    Passing `ui_visibility=["app"]` hides the tool from the model (app-only),
    per the extension; omit it for the default `["model", "app"]`.
    """
    ui_meta: dict[str, Any] = {"resourceUri": ui_resource_uri}
    if ui_visibility is not None:
        ui_meta["visibility"] = ui_visibility

    combined_meta: dict[str, Any] = {
        "ui": ui_meta,
        "io.modelcontextprotocol/ui": dict(ui_meta),
    }
    if openai_output_template is not None:
        combined_meta["openai/outputTemplate"] = openai_output_template
    if meta:
        combined_meta.update(meta)

    return register_tool(mcp, meta=combined_meta, **tool_kwargs)
