"""Tests for RosbridgeClient against the mock rosbridge server."""

from __future__ import annotations

import pytest

from rosbridge_mcp.client import RosbridgeClient, RosbridgeError

pytestmark = pytest.mark.asyncio


async def test_call_service_correlates_response(client):
    values = await client.call_service("/rosapi/nodes")
    assert values == {"nodes": ["/talker", "/listener", "/rosapi"]}


async def test_call_service_failure_raises(client):
    with pytest.raises(RosbridgeError, match="simulated failure"):
        await client.call_service("/fail")


async def test_collect_messages_unsubscribes(client, mock_rosbridge):
    messages = await client.collect_messages("/chatter", count=1, timeout=2.0)
    assert messages == [{"data": "hello from mock"}]
    assert "/chatter" in mock_rosbridge.subscribed
    # Give the unsubscribe frame a moment to arrive.
    import asyncio

    await asyncio.sleep(0.1)
    assert "/chatter" in mock_rosbridge.unsubscribed


async def test_publish_advertises_once(client, mock_rosbridge):
    import asyncio

    await client.publish("/cmd_vel", "geometry_msgs/msg/Twist", {"linear": {"x": 1}})
    await client.publish("/cmd_vel", "geometry_msgs/msg/Twist", {"linear": {"x": 2}})
    await asyncio.sleep(0.1)
    advertised = [a for a in mock_rosbridge.advertised if a["topic"] == "/cmd_vel"]
    assert len(advertised) == 1
    assert len(mock_rosbridge.published) == 2


async def test_reconnects_after_server_restart(mock_rosbridge):
    client = RosbridgeClient(url=mock_rosbridge.url)
    try:
        await client.call_service("/rosapi/nodes")
        assert client.connected
        # Restart the mock on the same port to simulate a dropped connection.
        port = int(mock_rosbridge.url.rsplit(":", 1)[1])
        await mock_rosbridge.stop()
        import asyncio

        await asyncio.sleep(0.1)
        assert not client.connected
        await mock_rosbridge.start(port)
        values = await client.call_service("/rosapi/services")
        assert "/rosapi/topics" in values["services"]
    finally:
        await client.close()


async def test_connect_error_message():
    client = RosbridgeClient(url="ws://127.0.0.1:1", connect_timeout=1.0)
    with pytest.raises(RosbridgeError, match="Cannot connect"):
        await client.call_service("/rosapi/nodes")
