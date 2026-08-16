"""MCP server exposing rosbridge-backed tools for AI agents.

Run with the ``rosbridge-mcp`` console script (stdio transport). Configuration
is done via environment variables:

- ``ROSBRIDGE_URL``: WebSocket URL of the rosbridge server
  (default ``ws://localhost:9090``).
- ``ROSBRIDGE_MCP_READONLY``: when truthy (``1``/``true``/``yes``), mutating
  tools (``publish_message`` and non-rosapi ``call_service``) are rejected.
"""

from __future__ import annotations

import os
from typing import Any

from fastmcp import FastMCP

from rosbridge_mcp.client import RosbridgeClient, RosbridgeError

mcp = FastMCP(
    "rosbridge-mcp",
    instructions=(
        "Bridge to a ROS 2 robot via rosbridge. Use list_topics/list_nodes/"
        "list_services to discover the robot graph, get_topic_snapshot to read "
        "sensor data, and publish_message/call_service to act on the robot."
    ),
)

_client: RosbridgeClient | None = None

# rosapi services that mutate state and are therefore blocked in readonly mode.
_MUTATING_ROSAPI = {"/rosapi/set_param", "/rosapi/delete_param"}


def get_client() -> RosbridgeClient:
    """Return the shared RosbridgeClient, creating it on first use."""
    global _client
    if _client is None:
        _client = RosbridgeClient()
    return _client


def is_readonly() -> bool:
    return os.environ.get("ROSBRIDGE_MCP_READONLY", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _readonly_error(action: str) -> dict[str, Any]:
    return {
        "error": (
            f"Rejected: {action} is disabled because ROSBRIDGE_MCP_READONLY is "
            "set. Unset it (or set it to 'false') to allow tools that can "
            "affect the robot."
        ),
        "readonly": True,
    }


# ---------------------------------------------------------------------- #
# Tool implementations (plain async functions, registered with mcp below)
# ---------------------------------------------------------------------- #


async def list_topics() -> dict[str, Any]:
    """List all ROS topics currently known to the robot, with message types.

    Takes no arguments. Returns {"topics": [{"name": "/scan", "type":
    "sensor_msgs/msg/LaserScan"}, ...]}. Call this first to discover what
    the robot exposes before subscribing or publishing.
    """
    client = get_client()
    result = await client.call_service("/rosapi/topics")
    topics = result.get("topics", [])
    types = result.get("types", [])
    if len(types) != len(topics):
        # Older rosapi versions may omit types; resolve them one by one.
        types = []
        for topic in topics:
            response = await client.call_service(
                "/rosapi/topic_type", {"topic": topic}
            )
            types.append(response.get("type", ""))
    return {
        "topics": [
            {"name": name, "type": type_} for name, type_ in zip(topics, types)
        ]
    }


async def list_nodes() -> dict[str, Any]:
    """List all ROS nodes currently running on the robot.

    Takes no arguments. Returns {"nodes": ["/talker", "/rosapi", ...]}.
    Useful to check whether an expected driver or controller is up.
    """
    result = await get_client().call_service("/rosapi/nodes")
    return {"nodes": result.get("nodes", [])}


async def list_services() -> dict[str, Any]:
    """List all ROS services currently available on the robot.

    Takes no arguments. Returns {"services": ["/reset_odometry", ...]}.
    Use before call_service to find the exact service name.
    """
    result = await get_client().call_service("/rosapi/services")
    return {"services": result.get("services", [])}


async def get_topic_snapshot(
    topic: str,
    count: int = 1,
    timeout: float = 5.0,
    msg_type: str | None = None,
) -> dict[str, Any]:
    """Read live data from a topic: subscribe, collect up to `count`
    messages (or until `timeout` seconds elapse), then unsubscribe.

    Args:
        topic: Topic name including leading slash, e.g. "/scan" or "/odom".
        count: How many messages to collect (default 1). Use more to observe
            a value changing over time.
        timeout: Max seconds to wait (default 5.0). The tool never blocks
            longer than this, even on a silent topic.
        msg_type: Optional full message type, e.g. "sensor_msgs/msg/LaserScan".
            Usually omit it; rosbridge resolves the type of existing topics.

    Returns {"topic", "requested", "received", "messages": [...], "timed_out"}.
    If "timed_out" is true, nothing (or not enough) was published within the
    timeout — the topic may be silent, misspelled, or not exist.
    """
    messages = await get_client().collect_messages(
        topic, count=count, timeout=timeout, msg_type=msg_type
    )
    return {
        "topic": topic,
        "requested": count,
        "received": len(messages),
        "messages": messages,
        "timed_out": len(messages) < count,
    }


async def publish_message(
    topic: str, msg_type: str, message: dict[str, Any]
) -> dict[str, Any]:
    """Publish a JSON message to a ROS topic (advertises the topic first).

    CAUTION: this can move a real robot. Rejected when ROSBRIDGE_MCP_READONLY
    is set. Prefer reading relevant sensor topics (e.g. /scan, /odom) before
    commanding motion, and publish zero velocity to stop.

    Args:
        topic: Target topic, e.g. "/cmd_vel".
        msg_type: Full ROS 2 message type with the "/msg/" segment, e.g.
            "geometry_msgs/msg/Twist" or "std_msgs/msg/String".
        message: JSON object whose fields match the message definition, e.g.
            {"linear": {"x": 0.1, "y": 0.0, "z": 0.0},
             "angular": {"x": 0.0, "y": 0.0, "z": 0.2}} for a Twist.
            Omitted fields default to zero/empty on the ROS side.

    Returns {"published": true, "topic": ..., "type": ...} on success.
    """
    if is_readonly():
        return _readonly_error("publish_message")
    await get_client().publish(topic, msg_type, message)
    return {"published": True, "topic": topic, "type": msg_type}


async def call_service(
    service: str,
    args: dict[str, Any] | None = None,
    timeout: float = 10.0,
) -> dict[str, Any]:
    """Call any ROS service with JSON args and return the response values.

    Rejected when ROSBRIDGE_MCP_READONLY is set, except read-only /rosapi/*
    introspection services.

    Args:
        service: Full service name, e.g. "/rosapi/topic_type" or
            "/reset_odometry". Discover names with list_services.
        args: JSON object matching the service request definition, e.g.
            {"topic": "/scan"} for /rosapi/topic_type. Default {}.
        timeout: Max seconds to wait for the response (default 10.0).

    Returns {"service", "success": true, "values": {...}} on success, or
    {"service", "success": false, "error": "..."} on failure/timeout.
    """
    if is_readonly():
        allowed = service.startswith("/rosapi/") and service not in _MUTATING_ROSAPI
        if not allowed:
            return _readonly_error(f"call_service({service})")
    try:
        values = await get_client().call_service(service, args, timeout=timeout)
    except RosbridgeError as exc:
        return {"service": service, "success": False, "error": str(exc)}
    return {"service": service, "success": True, "values": values}


async def get_connection_status() -> dict[str, Any]:
    """Report the current rosbridge connection status and readonly mode.

    Takes no arguments. Returns {"url", "connected", "connected_since_unix",
    "active_subscriptions", "pending_service_calls", "readonly"}. The
    connection is opened lazily, so "connected" is false until another tool
    has been used. Check this first when other tools report errors.
    """
    status = get_client().status()
    status["readonly"] = is_readonly()
    return status


for _tool in (
    list_topics,
    list_nodes,
    list_services,
    get_topic_snapshot,
    publish_message,
    call_service,
    get_connection_status,
):
    mcp.tool(_tool)


def main() -> None:
    """Console entry point: run the MCP server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
