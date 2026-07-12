"""Exception types shared across the server."""

from __future__ import annotations


class ToolInputError(ValueError):
    """A tool was called with invalid client-supplied input -- e.g. an unknown
    collection_id or an empty query.

    These are expected 4xx-style errors, not server faults. They must still
    propagate so the MCP SDK returns a helpful ``isError`` result to the client,
    but ``register_tool`` deliberately does *not* report them to Sentry/Better
    Stack (see server/registry.py). Subclass this for any new bad-input
    condition a tool raises so it stays out of the error tracker.

    Subclasses ``ValueError`` so existing ``pytest.raises(ValueError)`` and
    ``raise ValueError`` call sites keep working.
    """
