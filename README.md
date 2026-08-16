# rosbridge-mcp

[![CI](https://github.com/N4G/rosbridge-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/N4G/rosbridge-mcp/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)

**rosbridge-mcp** is a [Model Context Protocol](https://modelcontextprotocol.io) server that connects AI agents (Claude Desktop, Cursor, VS Code, and any other MCP client) to robots running **ROS 2**, via the standard [rosbridge v2 protocol](https://github.com/RosbridgeFoundation/rosbridge_suite) (WebSocket + JSON). You run `rosbridge_server` on your robot or ROS machine; this MCP server connects to it over the network and exposes tools that let the AI observe topics, inspect the ROS graph, publish messages, and call services — no ROS installation needed on the machine running the AI client.

## Architecture

```text
+--------------------+   stdio (MCP)   +----------------+   WebSocket/JSON   +------------------+   DDS   +---------+
|  AI client         | <-------------> | rosbridge-mcp  | <----------------> | rosbridge_server | <-----> |  ROS 2  |
|  (Claude, Cursor,  |                 |  (this server) |    rosbridge v2    |  (on the robot)  |         |  graph  |
|   VS Code, ...)    |                 |                |      protocol      |                  |         |         |
+--------------------+                 +----------------+                    +------------------+         +---------+
```

## Quick Start (60 seconds)

```bash
pip install rosbridge-mcp
```

Add to your MCP client config (see per-client guides below for exact file locations):

```json
{
  "mcpServers": {
    "rosbridge": {
      "command": "rosbridge-mcp",
      "env": { "ROSBRIDGE_URL": "ws://<robot-ip>:9090" }
    }
  }
}
```

Then ask your agent: *"What topics does the robot have?"*

## Choose your path

Pick the guide that matches you — each one is self-contained, you don't need to read the rest of this README first:

| You are... | Guide |
| --- | --- |
| **A Claude Desktop user** — want to talk to your robot from Claude | [docs/claude-desktop.md](docs/claude-desktop.md) |
| **A Cursor or VS Code user** — want robot tools inside your editor | [docs/cursor-vscode.md](docs/cursor-vscode.md) |
| **New to ROS, no robot yet** — try everything with a simulator or Docker, no hardware | [docs/simulator-quickstart.md](docs/simulator-quickstart.md) |
| **Connecting a real robot** — safety checklist before you let an LLM near hardware | [docs/real-robot-safety.md](docs/real-robot-safety.md) |
| **A developer** — want to contribute, add tools, or understand the code | [docs/development.md](docs/development.md) |

## Tools

All tools return JSON. Message and args payloads use the same JSON representation of ROS messages that rosbridge uses (field names match the `.msg`/`.srv` definitions).

### `list_topics`

List all topics with their message types. No parameters.

```json
{"topics": [
  {"name": "/chatter", "type": "std_msgs/msg/String"},
  {"name": "/cmd_vel", "type": "geometry_msgs/msg/Twist"},
  {"name": "/scan",    "type": "sensor_msgs/msg/LaserScan"}
]}
```

### `list_nodes`

List all running nodes. No parameters.

```json
{"nodes": ["/talker", "/listener", "/rosapi"]}
```

### `list_services`

List all available services. No parameters.

```json
{"services": ["/rosapi/topics", "/rosapi/nodes", "/reset_odometry"]}
```

### `get_topic_snapshot`

Subscribe to a topic, collect messages, unsubscribe. Parameters: `topic` (required), `count` (default 1), `timeout` seconds (default 5.0), `msg_type` (optional, usually auto-detected by rosbridge).

Input: `{"topic": "/chatter", "count": 2, "timeout": 3.0}`

```json
{"topic": "/chatter", "requested": 2, "received": 2,
 "messages": [{"data": "Hello World: 41"}, {"data": "Hello World: 42"}],
 "timed_out": false}
```

If the topic is silent, `received` is less than `requested` and `timed_out` is `true` — the tool never hangs longer than `timeout`.

### `publish_message` *(mutating)*

Advertise a topic and publish one JSON message. Parameters: `topic`, `msg_type` (full ROS 2 type, e.g. `geometry_msgs/msg/Twist`), `message` (JSON object matching the type).

Input:

```json
{"topic": "/cmd_vel", "msg_type": "geometry_msgs/msg/Twist",
 "message": {"linear": {"x": 0.1, "y": 0.0, "z": 0.0},
             "angular": {"x": 0.0, "y": 0.0, "z": 0.2}}}
```

Output: `{"published": true, "topic": "/cmd_vel", "type": "geometry_msgs/msg/Twist"}`

### `call_service` *(mutating)*

Call any ROS service. Parameters: `service` (required), `args` (JSON object, default `{}`), `timeout` seconds (default 10.0).

Input: `{"service": "/rosapi/topic_type", "args": {"topic": "/scan"}}`

```json
{"service": "/rosapi/topic_type", "success": true,
 "values": {"type": "sensor_msgs/msg/LaserScan"}}
```

On failure the tool returns `{"success": false, "error": "..."}` instead of raising.

### `get_connection_status`

Report connection state and readonly mode. No parameters.

```json
{"url": "ws://localhost:9090", "connected": true,
 "connected_since_unix": 1786903978.1, "active_subscriptions": [],
 "pending_service_calls": 0, "readonly": false}
```

## Example conversation

> **You:** What is the robot seeing right now?
>
> **Agent:** *(calls `list_topics`, finds `/scan` of type `sensor_msgs/msg/LaserScan`, then calls `get_topic_snapshot` with `{"topic": "/scan", "count": 1}`)*
> The laser scanner reports 360 range readings. The closest obstacle is about 0.4 m away at roughly 90° to the left; the space directly ahead is clear for at least 2.5 m.
>
> **You:** OK, drive forward slowly for a moment.
>
> **Agent:** *(calls `publish_message` with `{"topic": "/cmd_vel", "msg_type": "geometry_msgs/msg/Twist", "message": {"linear": {"x": 0.1}, "angular": {"z": 0.0}}}`)*
> Published a 0.1 m/s forward velocity command. Tell me when to stop and I'll publish zero velocity.

## Configuration

| Environment variable | Default | Description |
| --- | --- | --- |
| `ROSBRIDGE_URL` | `ws://localhost:9090` | WebSocket URL of the rosbridge server |
| `ROSBRIDGE_MCP_READONLY` | `false` | Reject mutating tools (see Safety) |

## Safety

Letting a language model publish `/cmd_vel` to a physical robot is a real risk. Set `ROSBRIDGE_MCP_READONLY=true` to run in **read-only mode**: `publish_message` is rejected, and `call_service` only permits read-only `/rosapi/*` introspection services (`set_param` / `delete_param` are still blocked). We strongly recommend starting in read-only mode with real hardware — see the full [real-robot safety checklist](docs/real-robot-safety.md) and the deployment security model in [SECURITY.md](SECURITY.md).

## Privacy & legal

**No telemetry, no data collection.** Audited (2026-08): the only network connection this package ever opens is the WebSocket to the `ROSBRIDGE_URL` you configure — there are no analytics, no phone-home, no crash reporting, no hidden HTTP calls, and the code contains no logging of message contents to disk. The bundled mock server binds to `127.0.0.1` only. Robot data returned by tools goes exclusively to your MCP client (which forwards it to the LLM you chose — that part is under your control, not ours).

**License compliance.** All runtime and transitive dependencies carry permissive licenses compatible with this project's MIT license — direct: `fastmcp` (Apache-2.0), `websockets` (BSD-3-Clause); key transitive: `mcp` (MIT), `pydantic` (MIT), `starlette` (BSD-3-Clause), `httpx` (BSD-3-Clause), `anyio` (MIT), `cryptography` (Apache-2.0/BSD-3). No GPL/AGPL/proprietary code anywhere in the dependency tree, and all code in this repository is original work written for this project.

## FAQ

**Do I need ROS installed where the AI client runs?**
No. Only Python 3.10+. ROS and rosbridge run on the robot (or in Docker, or in a simulator); this server talks to them over WebSocket.

**Does it work with ROS 1?**
The rosbridge v2 protocol is the same, so basic operations work against a ROS 1 `rosbridge_server` too — use ROS 1 type names (`std_msgs/String`). Only ROS 2 is tested in CI.

**The agent says it cannot connect.**
Check that rosbridge is running (`ros2 launch rosbridge_server rosbridge_websocket_launch.xml`), that `ROSBRIDGE_URL` points at the right host/port, and that port 9090 is reachable (firewall). Each guide in `docs/` has a troubleshooting section.

**Can I try it without any robot or simulator?**
Yes — `python -m rosbridge_mcp.mock_server 9090` starts a fake rosbridge with canned topics, then point `ROSBRIDGE_URL` at `ws://localhost:9090`.

**Is my data sent anywhere?**
The server only connects to the `ROSBRIDGE_URL` you configure. Topic data is returned to your MCP client, which forwards it to whatever LLM you use — treat sensor data accordingly.

## Roadmap

Staged plan with per-stage goals, deliverables, and the resources each stage needs: see [ROADMAP.md](ROADMAP.md). Highlights: v0.2 action client + TF + camera snapshots, v0.3 HTTP transport + Docker image + rosbridge auth/TLS, v0.4 multi-robot fleets + MCP resources (URDF/map), v1.0 stable API + official MCP registry listing + Gazebo/Isaac Sim examples.

## Contributing

Contributions are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) and the [development guide](docs/development.md). Please sign off your commits (DCO).

## License

MIT — see [LICENSE](LICENSE). Dependency licenses are permissive and compatible: `fastmcp` (Apache-2.0), `websockets` (BSD-3-Clause). No GPL/AGPL dependencies.

---

## Tóm tắt tiếng Việt

**rosbridge-mcp** là một MCP server cầu nối giữa AI agent (Claude Desktop, Cursor, VS Code...) và robot chạy ROS 2 thông qua giao thức rosbridge (WebSocket + JSON). Không cần cài ROS trên máy chạy AI client.

Tài liệu được chia theo từng kịch bản — chọn đúng hướng dẫn cho bạn trong thư mục `docs/`:

- [Dùng Claude Desktop](docs/claude-desktop.md) — cấu hình JSON từng bước trên Windows/macOS/Linux
- [Dùng Cursor / VS Code](docs/cursor-vscode.md) — cấu hình `mcp.json` trong editor
- [Chưa có robot](docs/simulator-quickstart.md) — chạy thử với Docker (`ros:humble` + rosbridge) hoặc TurtleBot3/Gazebo, hoặc mock server đi kèm
- [Có robot thật](docs/real-robot-safety.md) — checklist an toàn: bật `ROSBRIDGE_MCP_READONLY=true` trước, đọc `/odom`, `/scan` để hiểu robot rồi mới mở quyền publish `/cmd_vel`
- [Developer](docs/development.md) — kiến trúc code, cách thêm tool mới, chạy test với mock (không cần ROS)

7 tool: `list_topics`, `list_nodes`, `list_services`, `get_topic_snapshot`, `publish_message`, `call_service`, `get_connection_status`. Bật `ROSBRIDGE_MCP_READONLY=true` để chặn mọi thao tác ghi khi làm việc với robot thật.
