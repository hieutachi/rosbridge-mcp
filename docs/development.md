# Development guide

How the code is organized, how to add a tool, and how to test everything without ROS.

## Setup

```bash
git clone https://github.com/hieutachi/rosbridge-mcp.git
cd rosbridge-mcp
python -m venv .venv && . .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest
```

All tests run against an in-process mock rosbridge — no ROS, no Docker, no network access required. CI (`.github/workflows/ci.yml`) runs the same suite on Python 3.10 and 3.12.

## Architecture

```text
rosbridge_mcp/
├── client.py       RosbridgeClient — the protocol layer (no MCP knowledge)
├── server.py       FastMCP app + tool functions (no WebSocket knowledge)
├── mock_server.py  MockRosbridge — fake rosbridge for tests, demos, and manual runs
└── __init__.py     public exports
tests/
├── conftest.py     fixtures: mock_rosbridge, client, tools
├── test_client.py  protocol-level tests (correlation, reconnect, unsubscribe)
└── test_tools.py   tool-level tests (incl. readonly guardrails)
examples/
├── demo.py                     end-to-end script against the mock
├── claude_desktop_config.json  sample Claude Desktop config
└── cursor_mcp.json             sample Cursor config
```

**`RosbridgeClient`** (`client.py`) owns one WebSocket connection and implements the rosbridge v2 ops. Design points:

- *Lazy connect + transparent reconnect*: every operation calls `ensure_connected()`; if a send hits a closed connection, `_send()` reconnects once and retries.
- *Correlation*: each `call_service` gets a unique `id`; a background listener task resolves the matching future when a `service_response` with that `id` arrives.
- *Subscriptions*: `collect_messages()` registers an `asyncio.Queue` per snapshot, sends `subscribe`, drains the queue until `count` or `timeout`, then always unsubscribes.
- *Advertise-once*: `publish()` advertises each `(topic, type)` pair once per connection.

**`server.py`** holds the tool functions as plain async functions (registered with FastMCP at the bottom of the module). Keeping them plain functions means tests call them directly without going through the MCP transport. Readonly enforcement (`ROSBRIDGE_MCP_READONLY`) lives here, in `is_readonly()`, and is checked per call so tests can toggle it with `monkeypatch.setenv`.

**`mock_server.py`** speaks just enough rosbridge: `subscribe` replays canned messages from `topic_messages`, `call_service` answers rosapi services with fake graph data (and echoes unknown services; `/fail` simulates a failure), `publish`/`advertise`/`unsubscribe` are recorded in lists for assertions.

## Adding a new tool

1. Implement the rosbridge interaction in `RosbridgeClient` if it needs a new protocol op (see `collect_messages` for the subscribe pattern).
2. Add a plain async function in `server.py`. Write the docstring for an LLM audience: what it does, each parameter with an example value, and what the JSON result looks like — this text is the tool description the model sees.
3. Register it by adding it to the `for _tool in (...)` tuple at the bottom of `server.py`.
4. If it mutates robot state, add a readonly guard (`if is_readonly(): return _readonly_error(...)`) and a test proving the guard works.
5. Teach the mock: add the op handling or canned service response in `mock_server.py`.
6. Add tests in `tests/test_tools.py` (use the `tools` fixture) and update the tool table in `README.md`.

Example skeleton:

```python
async def get_param(name: str) -> dict[str, Any]:
    """Read a ROS parameter via /rosapi/get_param.

    Args:
        name: Fully-qualified parameter name, e.g. "/turtlebot3/max_vel".
    """
    values = await get_client().call_service("/rosapi/get_param", {"name": name})
    return {"name": name, "value": values.get("value")}
```

## Testing tips

- `pytest -v` — full suite; `pytest -k readonly` — just the guardrail tests.
- The `tools` fixture wires `server._client` to a fresh mock; the `mock_rosbridge` fixture exposes `.published`, `.advertised`, `.subscribed`, `.unsubscribed` for assertions.
- To poke around manually: `python -m rosbridge_mcp.mock_server 9090` in one terminal, `python examples/demo.py` (spins up its own mock) or an MCP client pointed at `ws://localhost:9090` in another.
- To test the MCP layer itself, FastMCP's in-memory client works: `async with Client(mcp) as c: await c.call_tool("list_topics", {})`.

## Conventions

- Conventional Commits (`feat:`, `fix:`, `docs:`...) and DCO sign-off (`git commit -s`) — see [CONTRIBUTING.md](../CONTRIBUTING.md).
- No new runtime dependencies without discussion; keep them permissively licensed (no GPL/AGPL).
- Behavior changes need tests. Docs-only changes should keep `pytest` green anyway (it's fast).

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `pytest` fails with `ModuleNotFoundError: rosbridge_mcp` | Install editable first: `pip install -e ".[dev]"`. |
| `RuntimeError: no running event loop` in new tests | Async tests need the `pytest.mark.asyncio` marker; both test modules set it via `pytestmark`. |
| Port conflicts in tests | Shouldn't happen — the mock binds port 0 (ephemeral). If you hardcoded 9090 in a test, don't. |
| Version mismatch with system packages | Use a venv. The pins are `fastmcp>=2,<3`, `websockets>=12,<16`. |
