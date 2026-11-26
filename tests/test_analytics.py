from typing import Any
from unittest.mock import Mock

import pytest
from mcp.server.fastmcp import FastMCP
from starlette.testclient import TestClient

from server import analytics


@pytest.mark.parametrize("capture_fails", [False, True])
def test_http_usage_survives_capture_failure_and_preserves_tool_results(
    monkeypatch: pytest.MonkeyPatch, capture_fails: bool
) -> None:
    sink = Mock()
    if capture_fails:
        sink.capture.side_effect = RuntimeError("offline")
        sink.shutdown.side_effect = RuntimeError("offline")
    monkeypatch.setenv("POSTHOG_PROJECT_TOKEN", "test-token")
    monkeypatch.setattr(analytics, "Posthog", Mock(return_value=sink))
    server = FastMCP("test-catalog", stateless_http=True, json_response=True)
    server._mcp_server.version = "1.2.3"

    @server.tool()
    async def lookup(query: str) -> str:
        if query == "fail":
            raise ValueError("invalid query")
        return "lookup-result"

    with TestClient(analytics.http_app(server), base_url="http://localhost:8000") as client:
        client.headers.update(
            {
                "Accept": "application/json, text/event-stream",
                "User-Agent": "private-agent-details",
                "X-Forwarded-For": "192.0.2.1",
            }
        )

        def rpc(method: str, params: dict[str, Any]) -> Any:
            return client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": method,
                    "params": params,
                },
            )

        response = rpc(
            "initialize",
            {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "test-client", "version": "2"},
            },
        )
        client.headers["Mcp-Session-Id"] = response.headers["Mcp-Session-Id"]
        client.headers["MCP-Protocol-Version"] = response.json()["result"]["protocolVersion"]
        assert rpc("tools/list", {}).json()["result"]["tools"][0]["name"] == "lookup"
        assert not rpc("tools/call", {"name": "lookup", "arguments": {"query": "wind"}}).json()[
            "result"
        ]["isError"]
        assert rpc("tools/call", {"name": "lookup", "arguments": {"query": "fail"}}).json()[
            "result"
        ]["isError"]
        del client.headers["Mcp-Session-Id"]
        for _ in range(2):
            rpc("tools/call", {"name": "lookup", "arguments": {"query": "wind"}})
    sink.flush.assert_called()
    sink.shutdown.assert_called_once()
    calls = sink.capture.call_args_list
    assert [call.args[0] for call in calls] == [
        "$mcp_initialize",
        "$mcp_tools_list",
        *["$mcp_tool_call"] * 4,
    ]
    if capture_fails:
        return
    for call in calls:
        props = call.kwargs["properties"]
        assert props["$mcp_source"] == "posthog_mcp_analytics"
        assert props["$process_person_profile"] is False
        assert props["$geoip_disable"] is True
        assert props["$mcp_server_version"] == "1.2.3"
        assert "$mcp_response" not in props
        assert "lookup-result" not in str(props)
        assert "192.0.2.1" not in str(props)
        assert "private-agent-details" not in str(props)
    props = calls[2].kwargs["properties"]
    assert props["$mcp_parameters"]["request"]["params"]["arguments"] == {"query": "wind"}
    assert props["$mcp_client_name"] == "test-client"
    assert props["$mcp_client_version"] == "2"
    assert props["$mcp_protocol_version"] == "2025-11-25"
    assert props["$mcp_duration_ms"] >= 0
    assert props["$mcp_is_error"] is False
    assert calls[3].kwargs["properties"]["$mcp_is_error"] is True
    assert calls[3].kwargs["properties"]["$mcp_error_type"] == "ValueError"
    assert calls[0].kwargs["distinct_id"] == calls[2].kwargs["distinct_id"]
    assert calls[4].kwargs["distinct_id"] != calls[5].kwargs["distinct_id"]


def test_missing_token_never_constructs_posthog(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("POSTHOG_PROJECT_TOKEN", raising=False)
    constructor = Mock(side_effect=AssertionError("PostHog initialized"))
    monkeypatch.setattr(analytics, "Posthog", constructor)
    with TestClient(analytics.http_app(FastMCP("test", stateless_http=True))) as client:
        assert client.get("/missing").status_code == 404
    constructor.assert_not_called()
