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


async def test_stale_listener_does_not_fail_new_calls(mock_rosbridge):
    """Issue #1: after a reconnect, the *old* connection's listener must not
    fail calls that are pending on the *new* connection."""
    import asyncio

    client = RosbridgeClient(url=mock_rosbridge.url)
    pending_key = "call_service:test-race"
    try:
        await client.ensure_connected()
        stale_ws = client._ws
        stale_task = client._listener_task
        # Simulate a detected drop followed by a reconnect: the stale
        # listener is still running on the old websocket.
        client._connected = False
        await client.ensure_connected()
        assert client._ws is not stale_ws
        # A call resent on the new connection is now pending.
        future = asyncio.get_running_loop().create_future()
        client._pending[pending_key] = future
        # The old connection finally dies; its listener exits.
        await stale_ws.close()
        await asyncio.wait_for(stale_task, 2)
        await asyncio.sleep(0.05)
        assert not future.done(), (
            "stale listener spuriously failed a call pending on the new "
            "connection"
        )
        assert client.connected
    finally:
        client._pending.pop(pending_key, None)
        await client.close()


async def test_status_errors_are_recorded(client, mock_rosbridge):
    """Issue #2: rosbridge 'status' warnings/errors are kept, not dropped."""
    import asyncio

    marker = client.status_error_marker
    await client.publish("/rejected", "not_a_real/msg/Type", {"x": 1})
    await asyncio.sleep(0.2)
    errors = client.status_errors_since(marker)
    assert errors, "expected the mock's status error to be recorded"
    assert errors[-1]["level"] == "error"
    assert "/rejected" in errors[-1]["msg"]


async def test_collect_messages_fails_fast_on_connection_loss(mock_rosbridge):
    """Issue #4: a collector on a silent topic aborts immediately when the
    connection drops, instead of sleeping out its full timeout."""
    import asyncio
    import time

    client = RosbridgeClient(url=mock_rosbridge.url)
    try:
        task = asyncio.create_task(
            client.collect_messages("/silent", count=1, timeout=30.0)
        )
        await asyncio.sleep(0.3)  # let the subscribe go out
        started = time.monotonic()
        await mock_rosbridge.stop()
        with pytest.raises(RosbridgeError, match="lost"):
            await asyncio.wait_for(task, 5)
        assert time.monotonic() - started < 5
    finally:
        await client.close()
