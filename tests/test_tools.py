"""Tests for the MCP tool functions exposed by rosbridge_mcp.server."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


async def test_list_topics(tools):
    result = await tools.list_topics()
    names = {t["name"]: t["type"] for t in result["topics"]}
    assert names["/chatter"] == "std_msgs/msg/String"
    assert names["/cmd_vel"] == "geometry_msgs/msg/Twist"


async def test_list_nodes(tools):
    result = await tools.list_nodes()
    assert result["nodes"] == ["/talker", "/listener", "/rosapi"]


async def test_list_services(tools):
    result = await tools.list_services()
    assert "/reset_odometry" in result["services"]


async def test_get_topic_snapshot_single(tools):
    result = await tools.get_topic_snapshot("/chatter", count=1, timeout=2.0)
    assert result["received"] == 1
    assert result["messages"] == [{"data": "hello from mock"}]
    assert result["timed_out"] is False


async def test_get_topic_snapshot_multiple(tools):
    result = await tools.get_topic_snapshot("/counter", count=3, timeout=2.0)
    assert result["received"] == 3
    assert [m["data"] for m in result["messages"]] == [0, 1, 2]


async def test_get_topic_snapshot_timeout_on_silent_topic(tools):
    result = await tools.get_topic_snapshot("/silent", count=1, timeout=0.3)
    assert result["received"] == 0
    assert result["messages"] == []
    assert result["timed_out"] is True


async def test_publish_message(tools, mock_rosbridge):
    import asyncio

    result = await tools.publish_message(
        "/cmd_vel", "geometry_msgs/msg/Twist", {"linear": {"x": 0.5}}
    )
    assert result["published"] is True
    await asyncio.sleep(0.1)
    assert mock_rosbridge.published[-1] == {
        "topic": "/cmd_vel",
        "msg": {"linear": {"x": 0.5}},
    }
    assert mock_rosbridge.advertised[-1]["type"] == "geometry_msgs/msg/Twist"


async def test_call_service_generic(tools):
    result = await tools.call_service("/reset_odometry", {"frame": "odom"})
    assert result["success"] is True
    assert result["values"]["echo"] == {"frame": "odom"}


async def test_call_service_failure_reported(tools):
    result = await tools.call_service("/fail")
    assert result["success"] is False
    assert "simulated failure" in result["error"]


async def test_get_connection_status(tools):
    before = await tools.get_connection_status()
    assert before["connected"] is False
    await tools.list_nodes()
    after = await tools.get_connection_status()
    assert after["connected"] is True
    assert after["url"].startswith("ws://127.0.0.1:")
    assert after["readonly"] is False


async def test_readonly_blocks_publish(tools, monkeypatch):
    monkeypatch.setenv("ROSBRIDGE_MCP_READONLY", "true")
    result = await tools.publish_message("/cmd_vel", "geometry_msgs/msg/Twist", {})
    assert result["readonly"] is True
    assert "Rejected" in result["error"]


async def test_readonly_blocks_arbitrary_service(tools, monkeypatch):
    monkeypatch.setenv("ROSBRIDGE_MCP_READONLY", "1")
    result = await tools.call_service("/reset_odometry")
    assert result["readonly"] is True
    assert "Rejected" in result["error"]


async def test_readonly_allows_rosapi_reads(tools, monkeypatch):
    monkeypatch.setenv("ROSBRIDGE_MCP_READONLY", "1")
    result = await tools.call_service("/rosapi/topics")
    assert result["success"] is True
    listed = await tools.list_topics()
    assert listed["topics"]


async def test_readonly_blocks_mutating_rosapi(tools, monkeypatch):
    monkeypatch.setenv("ROSBRIDGE_MCP_READONLY", "1")
    result = await tools.call_service("/rosapi/set_param", {"name": "x", "value": "1"})
    assert result["readonly"] is True


async def test_all_tools_registered():
    from rosbridge_mcp.server import mcp

    tool_names = set((await mcp.get_tools()).keys())
    assert {
        "list_topics",
        "list_nodes",
        "list_services",
        "get_topic_snapshot",
        "publish_message",
        "call_service",
        "get_connection_status",
    } <= tool_names
