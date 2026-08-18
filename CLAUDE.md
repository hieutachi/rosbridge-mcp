# CLAUDE.md

Project context for Claude Code. `rosbridge-mcp` is an MCP server that connects AI agents to ROS 2 robots over rosbridge (WebSocket + JSON). The client machine does **not** need a ROS install.

## Layout

- `rosbridge_mcp/client.py` — rosbridge v2 protocol client (WebSocket, reconnect, correlation)
- `rosbridge_mcp/server.py` — FastMCP app and 11 tools; readonly policy lives here
- `rosbridge_mcp/mock_server.py` — in-process fake rosbridge for tests and local demos
- `tests/` — pytest, no ROS/network required
- `docs/` — per-client and safety guides
- `examples/` — Claude Desktop / Cursor MCP configs and `demo.py`

## Run

```bash
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
pytest
rosbridge-mcp                   # stdio MCP server
```

Against a mock (no robot):

```bash
python -m rosbridge_mcp.mock_server 9090
# then ROSBRIDGE_URL=ws://localhost:9090
```

Install from Git: `pip install git+https://github.com/hieutachi/rosbridge-mcp.git`

## Environment

| Variable | Default | Meaning |
| --- | --- | --- |
| `ROSBRIDGE_URL` | `ws://localhost:9090` | rosbridge WebSocket |
| `ROSBRIDGE_MCP_READONLY` | unset/false | When `1`/`true`/`yes`, mutating tools are rejected |

Start real-robot sessions with readonly on. See `docs/real-robot-safety.md`.

## Tools

Read-only: `list_topics`, `list_nodes`, `list_services`, `get_topic_snapshot`, `get_tf_tree`, `get_camera_image`, `get_connection_status`.

Mutating (blocked in readonly): `publish_message`, `send_action_goal`, `cancel_action_goal`. `call_service` is mutating except a frozen allowlist of `/rosapi` introspection services in `READONLY_SAFE_ROSAPI`.

All tools return JSON. Message payloads use rosbridge's JSON mapping of ROS `.msg`/`.srv`/`.action` fields.

## Conventions

- Conventional Commits (`feat:`, `fix:`, `docs:`) and DCO (`git commit -s`)
- Do not add runtime dependencies without discussion; keep licenses permissive
- Do not expose rosbridge to the public internet; it has no auth by default
- Do not publish to PyPI unless explicitly asked
- Do not change `.github/workflows` unless the request includes workflow-scope access
