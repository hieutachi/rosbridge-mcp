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

## Quick Start

### 1. Run rosbridge on your ROS 2 machine / robot

```bash
sudo apt install ros-$ROS_DISTRO-rosbridge-suite
ros2 launch rosbridge_server rosbridge_websocket_launch.xml
```

This starts a WebSocket server on port 9090. Also make sure `rosapi` is running (it is included in the default launch file).

### 2. Install rosbridge-mcp (on the machine running your AI client)

```bash
pip install rosbridge-mcp
# or from source:
pip install git+https://github.com/N4G/rosbridge-mcp.git
```

### 3. Configure your MCP client

**Claude Desktop** (`claude_desktop_config.json`) or **Cursor** (`.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "rosbridge": {
      "command": "rosbridge-mcp",
      "env": {
        "ROSBRIDGE_URL": "ws://<robot-ip>:9090",
        "ROSBRIDGE_MCP_READONLY": "false"
      }
    }
  }
}
```

Then ask your agent things like *"What topics does the robot have?"* or *"Grab one laser scan from /scan and describe the surroundings."*

### Try it without a robot

A mock rosbridge server ships with the package:

```bash
python -m rosbridge_mcp.mock_server 9090   # terminal 1
python examples/demo.py                     # terminal 2
```

## Tools

| Tool | Description | Mutating |
| --- | --- | --- |
| `list_topics` | List all topics with their message types (`/rosapi/topics`) | No |
| `list_nodes` | List all running nodes (`/rosapi/nodes`) | No |
| `list_services` | List all available services (`/rosapi/services`) | No |
| `get_topic_snapshot` | Subscribe to a topic, collect N messages (default 1) or until timeout (default 5 s), return them as JSON, then unsubscribe | No |
| `publish_message` | Advertise a topic and publish a JSON message to it | **Yes** |
| `call_service` | Call any ROS service with JSON args | **Yes** |
| `get_connection_status` | Current rosbridge connection state and readonly mode | No |

## Configuration

| Environment variable | Default | Description |
| --- | --- | --- |
| `ROSBRIDGE_URL` | `ws://localhost:9090` | WebSocket URL of the rosbridge server |
| `ROSBRIDGE_MCP_READONLY` | `false` | Reject mutating tools (see Safety) |

## Safety

Letting a language model publish `/cmd_vel` to a physical robot is a real risk. Set `ROSBRIDGE_MCP_READONLY=true` to run in **read-only mode**: `publish_message` is rejected, and `call_service` only permits read-only `/rosapi/*` introspection services (`set_param` / `delete_param` are still blocked). This is a guardrail we strongly recommend when connecting an agent to real hardware for the first time. Additional defense in depth (rosbridge authentication, topic allow-lists, network isolation) is on the roadmap.

## Roadmap

- [ ] Topic/service allow- and deny-lists
- [ ] Action client support (`send_goal` / `cancel_goal`)
- [ ] rosbridge authentication (`auth` op) and TLS (`wss://`)
- [ ] MCP resources for continuous topic streams
- [ ] Message schema hints via `/rosapi/message_details`

## Development

```bash
git clone https://github.com/N4G/rosbridge-mcp.git
cd rosbridge-mcp
pip install -e ".[dev]"
pytest
```

Tests run entirely against an in-process mock rosbridge server — no ROS required.

## Contributing

Contributions are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md). Please sign off your commits (DCO).

## License

MIT — see [LICENSE](LICENSE). Dependency licenses are permissive and compatible: `fastmcp` (Apache-2.0), `websockets` (BSD-3-Clause). No GPL/AGPL dependencies.

---

## Tóm tắt tiếng Việt

**rosbridge-mcp** là một MCP server cầu nối giữa AI agent (Claude Desktop, Cursor, VS Code...) và robot chạy ROS 2 thông qua giao thức rosbridge (WebSocket + JSON). Bạn chạy `rosbridge_server` trên robot, cấu hình `ROSBRIDGE_URL` trỏ tới đó, và AI agent có thể liệt kê topic/node/service, đọc dữ liệu cảm biến, publish message và gọi service. Bật `ROSBRIDGE_MCP_READONLY=true` để chặn mọi thao tác ghi khi làm việc với robot thật. Không cần cài ROS trên máy chạy AI client; có sẵn mock server để thử nghiệm.
