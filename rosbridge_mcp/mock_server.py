"""In-process mock rosbridge server for tests and demos (no ROS required).

Speaks just enough of the rosbridge v2 protocol to exercise every tool:
``subscribe`` replays canned messages (including fake /tf, /tf_static and
camera topics), ``call_service`` answers rosapi calls with fake graph data
(and echoes anything else), ``publish``/``advertise`` are recorded for
inspection, and the ROS 2 action ops (``send_action_goal`` /
``cancel_action_goal``) answer with fake feedback and results. Publishing to
``/rejected`` triggers a rosbridge ``status`` error, and setting
``supports_actions = False`` simulates an old rosbridge without action
support.

Run standalone with ``python -m rosbridge_mcp.mock_server [port]``.
"""

from __future__ import annotations

import asyncio
import base64
import json
import sys
from typing import Any

import websockets

DEFAULT_TOPICS = {
    "/chatter": "std_msgs/msg/String",
    "/cmd_vel": "geometry_msgs/msg/Twist",
    "/scan": "sensor_msgs/msg/LaserScan",
    "/tf": "tf2_msgs/msg/TFMessage",
    "/tf_static": "tf2_msgs/msg/TFMessage",
    "/camera/image/compressed": "sensor_msgs/msg/CompressedImage",
    "/camera/image_raw": "sensor_msgs/msg/Image",
}
DEFAULT_NODES = ["/talker", "/listener", "/rosapi"]
DEFAULT_SERVICES = [
    "/rosapi/topics",
    "/rosapi/nodes",
    "/rosapi/services",
    "/rosapi/topic_type",
    "/reset_odometry",
]

# A few bytes that start like a real JPEG (SOI + APP0 marker).
FAKE_JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01"


def _tf_message(
    parent: str, child: str, x: float = 0.0, y: float = 0.0, z: float = 0.0
) -> dict[str, Any]:
    return {
        "transforms": [
            {
                "header": {"frame_id": parent},
                "child_frame_id": child,
                "transform": {
                    "translation": {"x": x, "y": y, "z": z},
                    "rotation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0},
                },
            }
        ]
    }


def _default_topic_messages() -> dict[str, list[Any]]:
    big_raw = base64.b64encode(b"\x00" * (4 * 1024 * 1024 + 64)).decode("ascii")
    return {
        "/chatter": [{"data": "hello from mock"}],
        "/counter": [{"data": 0}, {"data": 1}, {"data": 2}],
        "/tf": [_tf_message("odom", "base_link", x=1.0)],
        "/tf_static": [_tf_message("base_link", "laser", z=0.2)],
        "/camera/image/compressed": [
            {
                "header": {"frame_id": "camera"},
                "format": "jpeg",
                "data": base64.b64encode(FAKE_JPEG).decode("ascii"),
            }
        ],
        "/camera/image_raw": [
            {
                "header": {"frame_id": "camera"},
                "encoding": "rgb8",
                "width": 2,
                "height": 2,
                "step": 6,
                "data": base64.b64encode(b"\x01" * 12).decode("ascii"),
            }
        ],
        "/camera/huge_raw": [
            {
                "header": {"frame_id": "camera"},
                "encoding": "rgb8",
                "width": 1183,
                "height": 1183,
                "step": 3549,
                "data": big_raw,
            }
        ],
    }


class MockRosbridge:
    """A fake rosbridge server bound to an ephemeral localhost port."""

    def __init__(self) -> None:
        self.topics: dict[str, str] = dict(DEFAULT_TOPICS)
        self.nodes: list[str] = list(DEFAULT_NODES)
        self.services: list[str] = list(DEFAULT_SERVICES)
        # Messages replayed to a client right after it subscribes to a topic.
        self.topic_messages: dict[str, list[Any]] = _default_topic_messages()
        self.published: list[dict[str, Any]] = []
        self.advertised: list[dict[str, Any]] = []
        self.subscribed: list[str] = []
        self.unsubscribed: list[str] = []
        self.action_goals: list[dict[str, Any]] = []
        self.cancelled_goals: list[dict[str, Any]] = []
        # Set False to simulate an old rosbridge without action support:
        # action ops are answered with a 'status' error instead.
        self.supports_actions = True
        # Goals to actions whose name contains "slow" stay pending until
        # cancelled, so cancel_action_goal can be exercised.
        self._pending_goals: dict[str, tuple[Any, str]] = {}
        self._server: Any = None
        self.url: str = ""

    async def start(self, port: int = 0) -> None:
        self._server = await websockets.serve(
            self._handler, "127.0.0.1", port, max_size=2**24
        )
        actual_port = self._server.sockets[0].getsockname()[1]
        self.url = f"ws://127.0.0.1:{actual_port}"

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    async def _handler(self, websocket: Any) -> None:
        try:
            async for raw in websocket:
                msg = json.loads(raw)
                op = msg.get("op")
                if op == "subscribe":
                    topic = msg["topic"]
                    self.subscribed.append(topic)
                    for payload in self.topic_messages.get(topic, []):
                        await websocket.send(
                            json.dumps(
                                {"op": "publish", "topic": topic, "msg": payload}
                            )
                        )
                elif op == "unsubscribe":
                    self.unsubscribed.append(msg["topic"])
                elif op == "advertise":
                    self.advertised.append(
                        {"topic": msg["topic"], "type": msg.get("type", "")}
                    )
                    if msg["topic"] == "/rejected":
                        await websocket.send(
                            json.dumps(
                                {
                                    "op": "status",
                                    "level": "error",
                                    "id": msg.get("id"),
                                    "msg": (
                                        "Unable to advertise topic /rejected: "
                                        "unknown message type "
                                        + msg.get("type", "")
                                    ),
                                }
                            )
                        )
                elif op == "publish":
                    self.published.append(
                        {"topic": msg["topic"], "msg": msg.get("msg")}
                    )
                elif op == "call_service":
                    await websocket.send(json.dumps(self._service_response(msg)))
                elif op == "send_action_goal":
                    await self._handle_send_action_goal(websocket, msg)
                elif op == "cancel_action_goal":
                    await self._handle_cancel_action_goal(websocket, msg)
        except websockets.exceptions.ConnectionClosed:
            # Client dropped mid-conversation; nothing to clean up.
            pass

    async def _handle_send_action_goal(
        self, websocket: Any, msg: dict[str, Any]
    ) -> None:
        self.action_goals.append(msg)
        goal_id = msg.get("id")
        action = msg.get("action", "")
        if not self.supports_actions:
            await websocket.send(
                json.dumps(
                    {
                        "op": "status",
                        "level": "error",
                        "id": goal_id,
                        "msg": "Unknown operation: send_action_goal",
                    }
                )
            )
            return
        if "slow" in action:
            self._pending_goals[str(goal_id)] = (websocket, action)
            return
        if msg.get("feedback"):
            for progress in (0.5, 0.9):
                await websocket.send(
                    json.dumps(
                        {
                            "op": "action_feedback",
                            "id": goal_id,
                            "action": action,
                            "values": {"progress": progress},
                        }
                    )
                )
        await websocket.send(
            json.dumps(
                {
                    "op": "action_result",
                    "id": goal_id,
                    "action": action,
                    "values": {"ok": True, "echo_goal": msg.get("args")},
                    "status": 4,  # GoalStatus.STATUS_SUCCEEDED
                    "result": True,
                }
            )
        )

    async def _handle_cancel_action_goal(
        self, websocket: Any, msg: dict[str, Any]
    ) -> None:
        self.cancelled_goals.append(msg)
        goal_id = str(msg.get("id"))
        if not self.supports_actions:
            await websocket.send(
                json.dumps(
                    {
                        "op": "status",
                        "level": "error",
                        "id": msg.get("id"),
                        "msg": "Unknown operation: cancel_action_goal",
                    }
                )
            )
            return
        if goal_id in self._pending_goals:
            goal_ws, action = self._pending_goals.pop(goal_id)
            await goal_ws.send(
                json.dumps(
                    {
                        "op": "action_result",
                        "id": msg.get("id"),
                        "action": action,
                        "values": {},
                        "status": 5,  # GoalStatus.STATUS_CANCELED
                        "result": True,
                    }
                )
            )

    def _service_response(self, msg: dict[str, Any]) -> dict[str, Any]:
        service = msg.get("service", "")
        args = msg.get("args") or {}
        response: dict[str, Any] = {
            "op": "service_response",
            "id": msg.get("id"),
            "service": service,
            "result": True,
        }
        if service == "/rosapi/topics":
            response["values"] = {
                "topics": list(self.topics),
                "types": list(self.topics.values()),
            }
        elif service == "/rosapi/nodes":
            response["values"] = {"nodes": self.nodes}
        elif service == "/rosapi/services":
            response["values"] = {"services": self.services}
        elif service == "/rosapi/topic_type":
            response["values"] = {"type": self.topics.get(args.get("topic", ""), "")}
        elif service == "/fail":
            response["result"] = False
            response["values"] = "simulated failure"
        else:
            response["values"] = {"echo": args, "service": service}
        return response


async def _main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 9090
    mock = MockRosbridge()
    await mock.start(port)
    print(f"Mock rosbridge listening on {mock.url}", flush=True)
    await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(_main())
