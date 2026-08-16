"""In-process mock rosbridge server for tests and demos (no ROS required).

Speaks just enough of the rosbridge v2 protocol to exercise every tool:
``subscribe`` replays canned messages, ``call_service`` answers rosapi calls
with fake graph data (and echoes anything else), ``publish``/``advertise``
are recorded for inspection.

Run standalone with ``python -m rosbridge_mcp.mock_server [port]``.
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

import websockets

DEFAULT_TOPICS = {
    "/chatter": "std_msgs/msg/String",
    "/cmd_vel": "geometry_msgs/msg/Twist",
    "/scan": "sensor_msgs/msg/LaserScan",
}
DEFAULT_NODES = ["/talker", "/listener", "/rosapi"]
DEFAULT_SERVICES = [
    "/rosapi/topics",
    "/rosapi/nodes",
    "/rosapi/services",
    "/rosapi/topic_type",
    "/reset_odometry",
]


class MockRosbridge:
    """A fake rosbridge server bound to an ephemeral localhost port."""

    def __init__(self) -> None:
        self.topics: dict[str, str] = dict(DEFAULT_TOPICS)
        self.nodes: list[str] = list(DEFAULT_NODES)
        self.services: list[str] = list(DEFAULT_SERVICES)
        # Messages replayed to a client right after it subscribes to a topic.
        self.topic_messages: dict[str, list[Any]] = {
            "/chatter": [{"data": "hello from mock"}],
            "/counter": [{"data": 0}, {"data": 1}, {"data": 2}],
        }
        self.published: list[dict[str, Any]] = []
        self.advertised: list[dict[str, Any]] = []
        self.subscribed: list[str] = []
        self.unsubscribed: list[str] = []
        self._server: Any = None
        self.url: str = ""

    async def start(self, port: int = 0) -> None:
        self._server = await websockets.serve(self._handler, "127.0.0.1", port)
        actual_port = self._server.sockets[0].getsockname()[1]
        self.url = f"ws://127.0.0.1:{actual_port}"

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    async def _handler(self, websocket: Any) -> None:
        async for raw in websocket:
            msg = json.loads(raw)
            op = msg.get("op")
            if op == "subscribe":
                topic = msg["topic"]
                self.subscribed.append(topic)
                for payload in self.topic_messages.get(topic, []):
                    await websocket.send(
                        json.dumps({"op": "publish", "topic": topic, "msg": payload})
                    )
            elif op == "unsubscribe":
                self.unsubscribed.append(msg["topic"])
            elif op == "advertise":
                self.advertised.append(
                    {"topic": msg["topic"], "type": msg.get("type", "")}
                )
            elif op == "publish":
                self.published.append({"topic": msg["topic"], "msg": msg.get("msg")})
            elif op == "call_service":
                await websocket.send(json.dumps(self._service_response(msg)))

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
    print(f"Mock rosbridge listening on {mock.url}")
    await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(_main())
