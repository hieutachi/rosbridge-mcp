# Using rosbridge-mcp with Cursor or VS Code

Get robot tools inside your editor's AI agent. Self-contained guide.

## Prerequisites

- Python 3.10+ (`python --version`)
- A rosbridge server reachable over the network — real robot, [simulator/Docker](simulator-quickstart.md), or the bundled mock (`python -m rosbridge_mcp.mock_server 9090`)
- Cursor, or VS Code 1.99+ with GitHub Copilot (agent mode)

## Step 1 — Install rosbridge-mcp

```bash
pip install rosbridge-mcp
```

## Step 2a — Cursor

Create (or edit) one of:

- **Per project:** `.cursor/mcp.json` in your project root
- **Global:** `~/.cursor/mcp.json` (Windows: `C:\Users\<you>\.cursor\mcp.json`)

```json
{
  "mcpServers": {
    "rosbridge": {
      "command": "rosbridge-mcp",
      "env": {
        "ROSBRIDGE_URL": "ws://localhost:9090",
        "ROSBRIDGE_MCP_READONLY": "true"
      }
    }
  }
}
```

Then open **Cursor Settings → MCP** and make sure the `rosbridge` server is enabled (green dot). A copy of this config ships in [`examples/cursor_mcp.json`](../examples/cursor_mcp.json).

## Step 2b — VS Code (Copilot agent mode)

Create `.vscode/mcp.json` in your workspace (note: VS Code uses `servers`, not `mcpServers`):

```json
{
  "servers": {
    "rosbridge": {
      "type": "stdio",
      "command": "rosbridge-mcp",
      "env": {
        "ROSBRIDGE_URL": "ws://localhost:9090",
        "ROSBRIDGE_MCP_READONLY": "true"
      }
    }
  }
}
```

Open the Chat view, switch to **Agent** mode, click the tools icon, and enable the `rosbridge` tools. VS Code may show a "Start" code lens on top of the `mcp.json` — click it to launch the server.

## Step 3 — Try it

In the agent chat:

> Use the rosbridge tools: list the robot's topics, then grab one message from /chatter.

Set `ROSBRIDGE_MCP_READONLY` to `"false"` when you want the agent to publish or call non-rosapi services — read the [real-robot safety checklist](real-robot-safety.md) first if hardware is involved.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| Server shows red / "failed" in Cursor MCP settings | Run `rosbridge-mcp` in a terminal yourself — if the shell can't find it, use the absolute path to the executable in `"command"`. |
| Tools listed but calls fail with `Cannot connect to rosbridge` | rosbridge is not running or `ROSBRIDGE_URL` is wrong. From the same machine, verify port 9090 answers: `curl -sS -o NUL -w "%{http_code}" http://localhost:9090` returns a code (any code) if something listens; connection refused means nothing is listening. Check firewalls for remote hosts. |
| VS Code ignores the config | You used `mcpServers` instead of `servers`, or your VS Code is older than 1.99. |
| Changes to `mcp.json` have no effect | Restart the MCP server from the MCP settings UI (Cursor) or reload the window (VS Code). |
| Version mismatch errors on install | `pip install --upgrade rosbridge-mcp` pulls compatible `fastmcp>=2,<3` and `websockets>=12,<16`. Use a virtual environment if your system Python has conflicting pins. |
