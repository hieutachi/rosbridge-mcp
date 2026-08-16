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
    """List all ROS topics currently known to the robot, with message types."""
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
    """List all ROS nodes currently running on the robot."""
    result = await get_client().call_service("/rosapi/nodes")
    return {"nodes": result.get("nodes", [])}


async def list_services() -> dict[str, Any]:
    """List all ROS services currently available on the robot."""
    result = await get_client().call_service("/rosapi/services")
    return {"services": result.get("services", [])}


async def get_topic_snapshot(
    topic: str,
    count: int = 1,
    timeout: float = 5.0,
    msg_type: str | None = None,
) -> dict[str, Any]:
    """Subscribe to a topic, collect up to `count` messages (or until
    `timeout` seconds elapse), then unsubscribe. Returns the messages as JSON.
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

    Example: publish_message("/cmd_vel", "geometry_msgs/msg/Twist",
    {"linear": {"x": 0.1}, "angular": {"z": 0.0}}).
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
    """Call any ROS service with JSON args and return the response values."""
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
    """Report the current rosbridge connection status and readonly mode."""
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
