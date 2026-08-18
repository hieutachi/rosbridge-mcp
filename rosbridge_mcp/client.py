"""Async rosbridge (v2 protocol) WebSocket client.

Implements the subset of the rosbridge v2 protocol needed by the MCP tools:
``subscribe`` / ``unsubscribe`` / ``advertise`` / ``publish`` / ``call_service``
plus the ROS 2 action operations ``send_action_goal`` / ``cancel_action_goal``
(with incoming ``action_feedback`` / ``action_result``) and incoming ``status``
messages.

The client lazily connects on first use and transparently reconnects if the
connection drops between operations. Service calls and action goals are
correlated with their responses via unique ``id`` fields.
"""

from __future__ import annotations

import asyncio
import itertools
import json
import os
import time
from typing import Any

import websockets
from websockets.exceptions import ConnectionClosed

DEFAULT_ROSBRIDGE_URL = "ws://localhost:9090"

# Sentinel pushed into subscription queues when the connection is lost, so
# collectors fail fast instead of waiting out their full timeout.
_CONNECTION_LOST = object()

# Camera frames can exceed the websockets default of 1 MiB; allow up to 16 MiB.
MAX_MESSAGE_SIZE = 2**24

# How many rosbridge status warnings/errors to keep for diagnostics.
_STATUS_HISTORY_LIMIT = 50

ACTIONS_UNSUPPORTED_HINT = (
    "this rosbridge server does not appear to support action operations "
    "(send_action_goal / cancel_action_goal). Upgrade rosbridge_suite on the "
    "robot to a ROS 2 release that includes action support "
    "(https://github.com/RobotWebTools/rosbridge_suite)."
)


class RosbridgeError(Exception):
    """Raised when rosbridge reports a failure or the connection breaks."""


class RosbridgeClient:
    """Manages a single WebSocket connection to a rosbridge server."""

    def __init__(
        self,
        url: str | None = None,
        connect_timeout: float = 5.0,
    ) -> None:
        self.url = url or os.environ.get("ROSBRIDGE_URL", DEFAULT_ROSBRIDGE_URL)
        self.connect_timeout = connect_timeout
        self._ws: Any = None
        self._connected = False
        self._connected_at: float | None = None
        self._listener_task: asyncio.Task | None = None
        self._pending: dict[str, asyncio.Future] = {}
        self._subscriptions: dict[str, set[asyncio.Queue]] = {}
        self._advertised: set[tuple[str, str]] = set()
        self._id_counter = itertools.count(1)
        self._connect_lock = asyncio.Lock()
        # rosbridge 'status' messages with level warning/error, newest last.
        self._status_errors: list[dict[str, Any]] = []
        # Last 'action_feedback' values received, keyed by goal id.
        self._action_feedback: dict[str, Any] = {}

    # ------------------------------------------------------------------ #
    # Connection management
    # ------------------------------------------------------------------ #

    @property
    def connected(self) -> bool:
        return self._connected

    async def ensure_connected(self) -> None:
        """Connect (or reconnect) if there is no live connection."""
        if self._connected:
            return
        async with self._connect_lock:
            if self._connected:
                return
            try:
                self._ws = await asyncio.wait_for(
                    websockets.connect(self.url, max_size=MAX_MESSAGE_SIZE),
                    timeout=self.connect_timeout,
                )
            except Exception as exc:
                raise RosbridgeError(
                    f"Cannot connect to rosbridge at {self.url}: {exc}"
                ) from exc
            self._connected = True
            self._connected_at = time.time()
            # A fresh connection has no advertised topics on the server side.
            self._advertised.clear()
            self._listener_task = asyncio.ensure_future(self._listen())

    async def close(self) -> None:
        self._connected = False
        if self._listener_task is not None:
            self._listener_task.cancel()
            self._listener_task = None
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None
        self._fail_pending(RosbridgeError("Connection closed"))
        self._notify_connection_lost()

    def status(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "connected": self._connected,
            "connected_since_unix": self._connected_at if self._connected else None,
            "active_subscriptions": sorted(self._subscriptions),
            "pending_service_calls": len(self._pending),
        }

    # ------------------------------------------------------------------ #
    # rosbridge status tracking (issue #2)
    # ------------------------------------------------------------------ #

    @property
    def status_error_marker(self) -> int:
        """Opaque marker to pass to :meth:`status_errors_since` later."""
        return len(self._status_errors)

    def status_errors_since(self, marker: int) -> list[dict[str, Any]]:
        """Return rosbridge warning/error status messages received after
        *marker* was taken (see :attr:`status_error_marker`)."""
        return list(self._status_errors[marker:])

    # ------------------------------------------------------------------ #
    # rosbridge operations
    # ------------------------------------------------------------------ #

    async def call_service(
        self,
        service: str,
        args: dict[str, Any] | None = None,
        timeout: float = 10.0,
    ) -> dict[str, Any]:
        """Call a ROS service and return its response values."""
        await self.ensure_connected()
        call_id = f"call_service:{next(self._id_counter)}"
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[call_id] = future
        try:
            await self._send(
                {
                    "op": "call_service",
                    "id": call_id,
                    "service": service,
                    "args": args or {},
                }
            )
            return await asyncio.wait_for(future, timeout)
        except asyncio.TimeoutError as exc:
            raise RosbridgeError(
                f"Service call to {service} timed out after {timeout}s"
            ) from exc
        finally:
            self._pending.pop(call_id, None)

    async def collect_messages(
        self,
        topic: str,
        count: int = 1,
        timeout: float = 5.0,
        msg_type: str | None = None,
    ) -> list[Any]:
        """Subscribe to *topic*, collect up to *count* messages, unsubscribe.

        Raises :class:`RosbridgeError` immediately if the connection is lost
        while collecting (instead of silently waiting out the timeout).
        """
        await self.ensure_connected()
        queue: asyncio.Queue = asyncio.Queue()
        self._subscriptions.setdefault(topic, set()).add(queue)
        sub_id = f"subscribe:{next(self._id_counter)}"
        subscribe_msg: dict[str, Any] = {
            "op": "subscribe",
            "id": sub_id,
            "topic": topic,
        }
        if msg_type:
            subscribe_msg["type"] = msg_type
        messages: list[Any] = []
        deadline = time.monotonic() + timeout
        try:
            await self._send(subscribe_msg)
            while len(messages) < count:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                try:
                    item = await asyncio.wait_for(queue.get(), remaining)
                except asyncio.TimeoutError:
                    break
                if item is _CONNECTION_LOST:
                    raise RosbridgeError(
                        f"Connection to rosbridge lost while collecting "
                        f"messages from {topic}"
                    )
                messages.append(item)
        finally:
            listeners = self._subscriptions.get(topic)
            if listeners is not None:
                listeners.discard(queue)
                if not listeners:
                    self._subscriptions.pop(topic, None)
            if self._connected:
                try:
                    await self._send(
                        {"op": "unsubscribe", "id": sub_id, "topic": topic}
                    )
                except RosbridgeError:
                    pass
        return messages

    async def publish(
        self, topic: str, msg_type: str, message: dict[str, Any]
    ) -> None:
        """Advertise *topic* (once per connection) and publish *message*."""
        await self.ensure_connected()
        if (topic, msg_type) not in self._advertised:
            await self._send(
                {
                    "op": "advertise",
                    "id": f"advertise:{next(self._id_counter)}",
                    "topic": topic,
                    "type": msg_type,
                }
            )
            self._advertised.add((topic, msg_type))
        await self._send({"op": "publish", "topic": topic, "msg": message})

    async def send_action_goal(
        self,
        action: str,
        action_type: str,
        goal: dict[str, Any] | None = None,
        timeout: float = 60.0,
        wait_for_result: bool = True,
    ) -> dict[str, Any]:
        """Send a ROS 2 action goal via the rosbridge ``send_action_goal`` op.

        When *wait_for_result* is true, waits for the correlated
        ``action_result`` message and returns ``{"goal_id", "result",
        "status", "values", "last_feedback"}``. Otherwise returns
        ``{"goal_id", "result_pending": True}`` right after sending.
        """
        await self.ensure_connected()
        goal_id = f"send_action_goal:{next(self._id_counter)}"
        payload: dict[str, Any] = {
            "op": "send_action_goal",
            "id": goal_id,
            "action": action,
            "action_type": action_type,
            "args": goal or {},
            "feedback": wait_for_result,
        }
        if not wait_for_result:
            await self._send(payload)
            return {"goal_id": goal_id, "result_pending": True}

        marker = self.status_error_marker
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[goal_id] = future
        try:
            await self._send(payload)
            result_msg = await asyncio.wait_for(future, timeout)
        except asyncio.TimeoutError as exc:
            if self._unknown_op_reported(marker):
                raise RosbridgeError(ACTIONS_UNSUPPORTED_HINT) from exc
            raise RosbridgeError(
                f"Action goal to {action} got no result within {timeout}s. "
                "The action may still be running (increase timeout or use "
                "wait_for_result=false), or the robot's rosbridge may be too "
                "old to support actions — " + ACTIONS_UNSUPPORTED_HINT
            ) from exc
        except RosbridgeError as exc:
            if "unknown operation" in str(exc).lower():
                raise RosbridgeError(ACTIONS_UNSUPPORTED_HINT) from exc
            raise
        finally:
            self._pending.pop(goal_id, None)
            last_feedback = self._action_feedback.pop(goal_id, None)
        return {
            "goal_id": goal_id,
            "result": result_msg.get("result", False),
            "status": result_msg.get("status"),
            "values": result_msg.get("values"),
            "last_feedback": last_feedback,
        }

    async def cancel_action_goal(self, action: str, goal_id: str) -> None:
        """Cancel a previously sent action goal (``cancel_action_goal`` op)."""
        await self.ensure_connected()
        await self._send(
            {"op": "cancel_action_goal", "id": goal_id, "action": action}
        )

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #

    def _unknown_op_reported(self, marker: int) -> bool:
        return any(
            "unknown operation" in str(entry.get("msg", "")).lower()
            for entry in self.status_errors_since(marker)
        )

    async def _send(self, payload: dict[str, Any]) -> None:
        try:
            await self._ws.send(json.dumps(payload))
        except ConnectionClosed:
            # One transparent reconnect attempt, then retry the send.
            self._connected = False
            await self.ensure_connected()
            await self._ws.send(json.dumps(payload))

    async def _listen(self) -> None:
        ws = self._ws
        try:
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                except (TypeError, ValueError):
                    continue
                self._dispatch(msg)
        except Exception:
            pass
        finally:
            # Only tear down state if we are still the *current* connection.
            # A stale listener (superseded by a reconnect) must not fail
            # calls that were resent on the new connection (issue #1).
            if self._ws is ws:
                self._connected = False
                self._fail_pending(RosbridgeError("Connection to rosbridge lost"))
                self._notify_connection_lost()

    def _dispatch(self, msg: dict[str, Any]) -> None:
        op = msg.get("op")
        if op == "service_response":
            future = self._pending.get(msg.get("id", ""))
            if future is not None and not future.done():
                if msg.get("result", True):
                    future.set_result(msg.get("values") or {})
                else:
                    future.set_exception(
                        RosbridgeError(
                            f"Service {msg.get('service')} failed: {msg.get('values')}"
                        )
                    )
        elif op == "publish":
            for queue in self._subscriptions.get(msg.get("topic", ""), set()):
                queue.put_nowait(msg.get("msg"))
        elif op == "status":
            self._handle_status(msg)
        elif op == "action_feedback":
            goal_id = msg.get("id")
            if goal_id:
                self._action_feedback[goal_id] = msg.get("values")
        elif op == "action_result":
            future = self._pending.get(msg.get("id", ""))
            if future is not None and not future.done():
                future.set_result(msg)

    def _handle_status(self, msg: dict[str, Any]) -> None:
        """Record rosbridge 'status' warnings/errors instead of dropping them
        (issue #2), and fail any pending call the status refers to."""
        level = str(msg.get("level", "")).lower()
        if level not in ("warning", "error"):
            return
        entry = {
            "level": level,
            "msg": str(msg.get("msg", "")),
            "id": msg.get("id"),
            "received_at": time.time(),
        }
        self._status_errors.append(entry)
        if len(self._status_errors) > _STATUS_HISTORY_LIMIT:
            del self._status_errors[: -_STATUS_HISTORY_LIMIT]
        if level == "error" and entry["id"]:
            future = self._pending.get(entry["id"])
            if future is not None and not future.done():
                future.set_exception(
                    RosbridgeError(f"rosbridge error: {entry['msg']}")
                )

    def _fail_pending(self, error: Exception) -> None:
        for future in self._pending.values():
            if not future.done():
                future.set_exception(error)
        self._pending.clear()

    def _notify_connection_lost(self) -> None:
        """Wake up all active collectors so they fail fast (issue #4)."""
        for queues in self._subscriptions.values():
            for queue in queues:
                queue.put_nowait(_CONNECTION_LOST)
