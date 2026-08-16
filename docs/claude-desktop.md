# Using rosbridge-mcp with Claude Desktop

This guide takes you from zero to asking Claude about your robot. It is self-contained — you do not need to read anything else first.

## Prerequisites

- Python 3.10+ on the machine running Claude Desktop (`python --version`)
- A rosbridge server reachable over the network — either on a real robot / ROS machine, in [a simulator or Docker](simulator-quickstart.md), or the bundled mock (`python -m rosbridge_mcp.mock_server 9090`)
- Claude Desktop installed and signed in

## Step 1 — Install rosbridge-mcp

```bash
pip install rosbridge-mcp
```

Verify the command is on your PATH (prints the executable's location):

```bash
where rosbridge-mcp    # Windows
which rosbridge-mcp    # macOS / Linux
```

If the command is not found, `pip show -f rosbridge-mcp` shows where the script was installed; make sure that `Scripts/` (Windows) or `bin/` directory is on your PATH, or use the full path to the executable in the config below.

## Step 2 — Locate the Claude Desktop config file

| OS | Path |
| --- | --- |
| Windows | `%APPDATA%\Claude\claude_desktop_config.json` |
| macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Linux | `~/.config/Claude/claude_desktop_config.json` |

You can also open it from Claude Desktop: **Settings → Developer → Edit Config**. If the file does not exist, create it with the content below.

## Step 3 — Add the server

Merge this into the config (replace `<robot-ip>` with the IP of the machine running rosbridge; use `localhost` if it runs on the same machine):

```json
{
  "mcpServers": {
    "rosbridge": {
      "command": "rosbridge-mcp",
      "env": {
        "ROSBRIDGE_URL": "ws://<robot-ip>:9090",
        "ROSBRIDGE_MCP_READONLY": "true"
      }
    }
  }
}
```

Notes:

- Start with `ROSBRIDGE_MCP_READONLY: "true"` — Claude can look but not touch. Switch to `"false"` once you have read the [real-robot safety checklist](real-robot-safety.md) (or if you are on a simulator/mock and want to experiment freely).
- On Windows, if `rosbridge-mcp` is not on PATH, use the full path, e.g. `"command": "C:\\Users\\you\\AppData\\Local\\Programs\\Python\\Python312\\Scripts\\rosbridge-mcp.exe"`.

## Step 4 — Restart Claude Desktop

Fully quit (Windows: right-click tray icon → Quit; macOS: Cmd+Q) and reopen. Under the tools icon in the chat input you should see the `rosbridge` server with 7 tools.

## Step 5 — Try it

Ask:

> What topics does the robot have, and what nodes are running?

Claude should call `list_topics` and `list_nodes`. Then:

> Grab one message from /chatter and show it to me.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| Server does not appear in Claude | Config file is invalid JSON (validate it), or Claude was not fully restarted. Check logs: `%APPDATA%\Claude\logs\mcp*.log` (Windows) or `~/Library/Logs/Claude/mcp*.log` (macOS). |
| `spawn rosbridge-mcp ENOENT` in logs | The command is not on the PATH Claude uses. Use the absolute path to the executable in `"command"`. |
| Tools appear but every call returns `Cannot connect to rosbridge at ...` | rosbridge is not running, or `ROSBRIDGE_URL` is wrong. Test reachability: `python -c "import websockets, asyncio; asyncio.run(websockets.connect('ws://<robot-ip>:9090'))"` — no output means success. Check firewalls on both machines allow TCP 9090. |
| `publish_message` returns `Rejected: ... ROSBRIDGE_MCP_READONLY` | Working as intended. Set `ROSBRIDGE_MCP_READONLY` to `"false"` in the config and restart Claude when you are ready. |
| Service calls time out but topics work | The `rosapi` node is not running on the ROS side. Use the default rosbridge launch file, which includes it: `ros2 launch rosbridge_server rosbridge_websocket_launch.xml`. |
