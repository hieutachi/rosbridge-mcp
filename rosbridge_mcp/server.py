"""MCP server exposing rosbridge-backed tools for AI agents.

Run with the ``rosbridge-mcp`` console script (stdio transport). Configuration
is done via environment variables:

- ``ROSBRIDGE_URL``: WebSocket URL of the rosbridge server
  (default ``ws://localhost:9090``).
- ``ROSBRIDGE_MCP_READONLY``: when truthy (``1``/``true``/``yes``), mutating
  tools (``publish_message``, ``send_action_goal``, ``cancel_action_goal``,
  and any ``call_service`` outside a fixed allowlist of read-only ``/rosapi``
  introspection services) are rejected.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import os
from typing import Any

from fastmcp import FastMCP

from rosbridge_mcp.client import (
    ACTIONS_UNSUPPORTED_HINT,
    RosbridgeClient,
    RosbridgeError,
)

mcp = FastMCP(
    "rosbridge-mcp",
    instructions=(
        "Bridge to a ROS 2 robot via rosbridge. Use list_topics/list_nodes/"
        "list_services to discover the robot graph, get_topic_snapshot to read "
        "sensor data, get_tf_tree for the coordinate-frame tree, "
        "get_camera_image to see through the robot's camera, and "
        "publish_message/call_service/send_action_goal to act on the robot."
    ),
)

_client: RosbridgeClient | None = None

# Readonly mode uses an *allowlist* (issue #3): only these known read-only
# rosapi introspection services may be called. Anything else — including
# unknown or future /rosapi services — is rejected.
READONLY_SAFE_ROSAPI = frozenset(
    {
        "/rosapi/topics",
        "/rosapi/topics_and_raw_types",
        "/rosapi/topics_for_type",
        "/rosapi/topic_type",
        "/rosapi/nodes",
        "/rosapi/node_details",
        "/rosapi/services",
        "/rosapi/services_for_type",
        "/rosapi/service_type",
        "/rosapi/service_providers",
        "/rosapi/service_node",
        "/rosapi/service_request_details",
        "/rosapi/service_response_details",
        "/rosapi/message_details",
        "/rosapi/publishers",
        "/rosapi/subscribers",
        "/rosapi/action_servers",
        "/rosapi/interfaces",
        "/rosapi/get_param",
        "/rosapi/get_param_names",
        "/rosapi/has_param",
        "/rosapi/get_time",
    }
)

# GoalStatus values from action_msgs/msg/GoalStatus (ROS 2).
_GOAL_STATUS_TEXT = {
    0: "unknown",
    1: "accepted",
    2: "executing",
    3: "canceling",
    4: "succeeded",
    5: "canceled",
    6: "aborted",
}

# How long to wait after fire-and-forget ops for a rosbridge 'status' error.
_STATUS_GRACE_S = 0.2

_MAX_IMAGE_BYTES = 4 * 1024 * 1024


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
        count: How many messages to collect (default 1, clamped to at most
            100). Use more to observe a value changing over time.
        timeout: Max seconds to wait (default 5.0, clamped to at most 60.0).
            The tool never blocks longer than this, even on a silent topic.
        msg_type: Optional full message type, e.g. "sensor_msgs/msg/LaserScan".
            Usually omit it; rosbridge resolves the type of existing topics.

    Returns {"topic", "requested", "received", "messages": [...], "timed_out",
    "timeout_s"}. If "timed_out" is true, nothing (or not enough) was
    published within the timeout — the topic may be silent, misspelled, or
    not exist. If the rosbridge connection drops mid-collection, the tool
    returns immediately with {"error", "connection_lost": true} instead of
    waiting out the timeout.
    """
    count = max(1, min(int(count), 100))
    timeout = max(0.1, min(float(timeout), 60.0))
    try:
        messages = await get_client().collect_messages(
            topic, count=count, timeout=timeout, msg_type=msg_type
        )
    except RosbridgeError as exc:
        return {
            "topic": topic,
            "requested": count,
            "error": str(exc),
            "connection_lost": True,
        }
    return {
        "topic": topic,
        "requested": count,
        "received": len(messages),
        "messages": messages,
        "timed_out": len(messages) < count,
        "timeout_s": timeout,
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

    Returns {"published": true, "topic": ..., "type": ...} on success. The
    tool briefly waits for rosbridge 'status' errors after publishing; if
    rosbridge rejected the message (e.g. wrong msg_type), the result includes
    "rosbridge_warnings" — treat those as the publish having failed.
    """
    if is_readonly():
        return _readonly_error("publish_message")
    client = get_client()
    marker = client.status_error_marker
    await client.publish(topic, msg_type, message)
    await asyncio.sleep(_STATUS_GRACE_S)
    warnings = [e["msg"] for e in client.status_errors_since(marker)]
    result: dict[str, Any] = {"published": True, "topic": topic, "type": msg_type}
    if warnings:
        result["rosbridge_warnings"] = warnings
        result["note"] = (
            "rosbridge reported a problem right after this publish; the "
            "message most likely did not reach the topic. Check msg_type "
            "and message fields."
        )
    return result


async def call_service(
    service: str,
    args: dict[str, Any] | None = None,
    timeout: float = 10.0,
) -> dict[str, Any]:
    """Call any ROS service with JSON args and return the response values.

    Rejected when ROSBRIDGE_MCP_READONLY is set, unless the service is on the
    fixed allowlist of known read-only /rosapi introspection services
    (topics, nodes, services, *_type, *_details, get_param, get_time, ...).

    Args:
        service: Full service name, e.g. "/rosapi/topic_type" or
            "/reset_odometry". Discover names with list_services.
        args: JSON object matching the service request definition, e.g.
            {"topic": "/scan"} for /rosapi/topic_type. Default {}.
        timeout: Max seconds to wait for the response (default 10.0).

    Returns {"service", "success": true, "values": {...}} on success, or
    {"service", "success": false, "error": "..."} on failure/timeout (with
    any related rosbridge status errors under "rosbridge_status").
    """
    if is_readonly() and service not in READONLY_SAFE_ROSAPI:
        return _readonly_error(f"call_service({service})")
    client = get_client()
    marker = client.status_error_marker
    try:
        values = await client.call_service(service, args, timeout=timeout)
    except RosbridgeError as exc:
        failure: dict[str, Any] = {
            "service": service,
            "success": False,
            "error": str(exc),
        }
        status_msgs = [e["msg"] for e in client.status_errors_since(marker)]
        if status_msgs:
            failure["rosbridge_status"] = status_msgs
        return failure
    return {"service": service, "success": True, "values": values}


async def send_action_goal(
    action_name: str,
    action_type: str,
    goal: dict[str, Any] | None = None,
    timeout: float = 30.0,
    wait_for_result: bool = True,
) -> dict[str, Any]:
    """Send a goal to a ROS 2 action server via rosbridge.

    CAUTION: actions typically make the robot move (navigation, arm motion).
    Rejected when ROSBRIDGE_MCP_READONLY is set.

    Args:
        action_name: Action name, e.g. "/navigate_to_pose".
        action_type: Full action type with the "/action/" segment, e.g.
            "nav2_msgs/action/NavigateToPose".
        goal: JSON object matching the action's goal definition. Default {}.
        timeout: Max seconds to wait for the result when wait_for_result is
            true (default 30.0, clamped to at most 120.0).
        wait_for_result: If true (default), block until the action finishes
            and return its result. If false, return the goal_id immediately —
            use cancel_action_goal with that id to stop the goal later.

    Returns, when waiting: {"action", "goal_id", "success", "status",
    "status_text" (succeeded/aborted/canceled/...), "values" (result fields),
    "last_feedback" (most recent feedback values, or null)}. When not
    waiting: {"action", "goal_id", "result_pending": true}.

    Requires rosbridge_suite with ROS 2 action support (ops send_action_goal
    / cancel_action_goal). Against an older rosbridge the tool detects the
    rejected operation (via rosbridge status errors, or timeout as fallback)
    and returns an error advising to upgrade rosbridge_suite on the robot.
    """
    if is_readonly():
        return _readonly_error("send_action_goal")
    timeout = max(1.0, min(float(timeout), 120.0))
    client = get_client()
    marker = client.status_error_marker
    try:
        if wait_for_result:
            outcome = await client.send_action_goal(
                action_name,
                action_type,
                goal,
                timeout=timeout,
                wait_for_result=True,
            )
        else:
            outcome = await client.send_action_goal(
                action_name, action_type, goal, wait_for_result=False
            )
            await asyncio.sleep(_STATUS_GRACE_S)
            if client._unknown_op_reported(marker):
                return {
                    "action": action_name,
                    "success": False,
                    "error": (
                        "send_action_goal was rejected: "
                        + ACTIONS_UNSUPPORTED_HINT
                    ),
                }
            return {
                "action": action_name,
                "goal_id": outcome["goal_id"],
                "result_pending": True,
            }
    except RosbridgeError as exc:
        return {"action": action_name, "success": False, "error": str(exc)}
    status = outcome.get("status")
    return {
        "action": action_name,
        "goal_id": outcome["goal_id"],
        "success": bool(outcome.get("result")),
        "status": status,
        "status_text": _GOAL_STATUS_TEXT.get(status, "unknown"),
        "values": outcome.get("values"),
        "last_feedback": outcome.get("last_feedback"),
    }


async def cancel_action_goal(action_name: str, goal_id: str) -> dict[str, Any]:
    """Cancel a previously sent ROS 2 action goal.

    Rejected when ROSBRIDGE_MCP_READONLY is set.

    Args:
        action_name: The action the goal was sent to, e.g.
            "/navigate_to_pose".
        goal_id: The goal_id returned by send_action_goal.

    Returns {"cancel_sent": true, "action", "goal_id"}. The cancellation
    outcome (status "canceled") is reported by the action server via the
    goal's result. Requires rosbridge_suite with ROS 2 action support; on an
    older rosbridge the tool returns an error advising an upgrade.
    """
    if is_readonly():
        return _readonly_error("cancel_action_goal")
    client = get_client()
    marker = client.status_error_marker
    await client.cancel_action_goal(action_name, goal_id)
    await asyncio.sleep(_STATUS_GRACE_S)
    if client._unknown_op_reported(marker):
        return {
            "action": action_name,
            "goal_id": goal_id,
            "cancel_sent": False,
            "error": "cancel_action_goal was rejected: "
            + ACTIONS_UNSUPPORTED_HINT,
        }
    return {"cancel_sent": True, "action": action_name, "goal_id": goal_id}


async def get_tf_tree(timeout: float = 2.0) -> dict[str, Any]:
    """Snapshot the robot's TF (coordinate transform) tree.

    Subscribes briefly to /tf and /tf_static, merges every transform seen
    into a parent→child frame tree. Read-only — works in readonly mode.
    Useful for spatial reasoning: which frames exist (map, odom, base_link,
    camera, gripper, ...) and how they are connected.

    Args:
        timeout: Seconds to listen for transforms (default 2.0, clamped to
            at most 10.0). Static transforms are latched and arrive
            immediately; dynamic ones need the robot to be publishing.

    Returns {"frame_count", "frames": {child_frame: {"parent", "translation":
    {x,y,z}, "rotation": {x,y,z,w}, "source": "static"|"dynamic"}}, "tree":
    {parent: [children...]}, "roots": [frames with no parent seen]}. An empty
    tree usually means nothing publishes /tf on this robot (or the listen
    window was too short).
    """
    timeout = max(0.2, min(float(timeout), 10.0))
    client = get_client()
    try:
        static_msgs, dynamic_msgs = await asyncio.gather(
            client.collect_messages(
                "/tf_static",
                count=1000,
                timeout=timeout,
                msg_type="tf2_msgs/msg/TFMessage",
            ),
            client.collect_messages(
                "/tf",
                count=1000,
                timeout=timeout,
                msg_type="tf2_msgs/msg/TFMessage",
            ),
        )
    except RosbridgeError as exc:
        return {"error": str(exc), "connection_lost": True}
    frames: dict[str, dict[str, Any]] = {}
    for source, msgs in (("static", static_msgs), ("dynamic", dynamic_msgs)):
        for msg in msgs:
            for tf in (msg or {}).get("transforms", []):
                child = tf.get("child_frame_id", "")
                if not child:
                    continue
                transform = tf.get("transform", {})
                frames[child] = {
                    "parent": tf.get("header", {}).get("frame_id", ""),
                    "translation": transform.get("translation"),
                    "rotation": transform.get("rotation"),
                    "source": source,
                }
    tree: dict[str, list[str]] = {}
    for child, info in frames.items():
        tree.setdefault(info["parent"], []).append(child)
    for children in tree.values():
        children.sort()
    roots = sorted(parent for parent in tree if parent not in frames)
    return {
        "frame_count": len(frames),
        "frames": frames,
        "tree": tree,
        "roots": roots,
        "listened_s": timeout,
    }


async def get_camera_image(topic: str, timeout: float = 5.0) -> dict[str, Any]:
    """Grab one frame from a camera topic, for vision-capable models.

    Read-only — works in readonly mode. Subscribes to *topic*, waits for one
    sensor_msgs/msg/CompressedImage (preferred) or sensor_msgs/msg/Image
    (raw) message, and returns the frame as base64. This is the bridge for
    VLM / vision-language-action workflows: the model can literally look
    through the robot's camera before deciding how to act.

    Args:
        topic: Camera topic, e.g. "/camera/image_raw/compressed". Prefer a
            compressed topic — raw images are large and may exceed the size
            limit below.
        timeout: Max seconds to wait for a frame (default 5.0, clamped to
            at most 30.0).

    Returns {"topic", "format" (e.g. "jpeg"), "data_base64", "size_bytes"},
    plus "width"/"height"/"encoding" for raw images. Frames larger than 4 MB
    are not returned: the tool responds with an error suggesting a
    CompressedImage topic instead (raw metadata is still included).
    """
    timeout = max(0.2, min(float(timeout), 30.0))
    try:
        messages = await get_client().collect_messages(
            topic, count=1, timeout=timeout
        )
    except RosbridgeError as exc:
        return {"topic": topic, "error": str(exc), "connection_lost": True}
    if not messages:
        return {
            "topic": topic,
            "error": (
                f"No image received on {topic} within {timeout}s. Check the "
                "topic name with list_topics and that the camera is running."
            ),
            "timed_out": True,
        }
    msg = messages[0] or {}
    raw_data = msg.get("data", "")
    if isinstance(raw_data, list):
        # Some rosbridge versions encode uint8[] as a JSON int array.
        data_bytes = bytes(bytearray(x & 0xFF for x in raw_data))
        data_b64 = base64.b64encode(data_bytes).decode("ascii")
        size_bytes = len(data_bytes)
    elif isinstance(raw_data, str):
        data_b64 = raw_data
        try:
            size_bytes = len(base64.b64decode(raw_data, validate=False))
        except (binascii.Error, ValueError):
            return {
                "topic": topic,
                "error": "Message 'data' field is not valid base64.",
            }
    else:
        return {
            "topic": topic,
            "error": (
                f"Message on {topic} has no image 'data' field — is this a "
                "sensor_msgs/msg/CompressedImage or sensor_msgs/msg/Image "
                "topic?"
            ),
        }
    result: dict[str, Any] = {"topic": topic, "size_bytes": size_bytes}
    if "format" in msg:  # sensor_msgs/msg/CompressedImage
        result["format"] = msg.get("format")
    elif "encoding" in msg:  # sensor_msgs/msg/Image (raw)
        result["format"] = f"raw ({msg.get('encoding')})"
        result["encoding"] = msg.get("encoding")
        result["width"] = msg.get("width")
        result["height"] = msg.get("height")
    else:
        return {
            "topic": topic,
            "error": (
                f"Message on {topic} does not look like an image (no "
                "'format' or 'encoding' field)."
            ),
        }
    if size_bytes > _MAX_IMAGE_BYTES:
        result["error"] = (
            f"Image is {size_bytes} bytes (> {_MAX_IMAGE_BYTES} limit). Use a "
            "CompressedImage topic instead (e.g. add '/compressed' — "
            "image_transport republishes most cameras as "
            "sensor_msgs/msg/CompressedImage)."
        )
        return result
    result["data_base64"] = data_b64
    return result


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
    send_action_goal,
    cancel_action_goal,
    get_tf_tree,
    get_camera_image,
    get_connection_status,
):
    mcp.tool(_tool)


def main() -> None:
    """Console entry point: run the MCP server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
