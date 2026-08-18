# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-08-18

### Added

- `send_action_goal` tool: send a goal to a ROS 2 action server via the
  rosbridge `send_action_goal` op; waits for the result (timeout clamped to
  120 s) with the last feedback received, or returns a `goal_id` immediately
  with `wait_for_result=false`. Detects rosbridge servers without action
  support and advises upgrading `rosbridge_suite`.
- `cancel_action_goal` tool: cancel an in-flight action goal by `goal_id`.
- `get_tf_tree` tool: brief subscription to `/tf` + `/tf_static` (clamped to
  10 s) merged into a parent→child frame tree with static/dynamic provenance.
- `get_camera_image` tool: grab one `sensor_msgs/msg/CompressedImage` or raw
  `Image` frame as base64 for vision-capable models, with a 4 MB safety limit
  and a hint to use compressed topics. WebSocket message size limit raised to
  16 MiB to fit camera frames.
- Mock rosbridge: fake action goal/feedback/result/cancel flows, an
  "old rosbridge without actions" mode, `/tf` + `/tf_static` frames, fake
  compressed/raw/oversized camera topics, and simulated `status` errors.
- `CHANGELOG.md` (this file).

### Fixed

- Reconnect race: a stale listener from a superseded connection no longer
  spuriously fails service calls that were resent on the new connection
  ([#1](https://github.com/hieutachi/rosbridge-mcp/issues/1)).
- rosbridge `status` messages are no longer silently dropped:
  `publish_message` now reports `rosbridge_warnings` when rosbridge rejects
  the message (e.g. wrong `msg_type`), and `call_service` failures include
  related status errors
  ([#2](https://github.com/hieutachi/rosbridge-mcp/issues/2)).
- `get_topic_snapshot` clamps `count` to ≤ 100 and `timeout` to ≤ 60 s, and
  fails fast when the connection drops mid-collection instead of waiting out
  the full timeout
  ([#4](https://github.com/hieutachi/rosbridge-mcp/issues/4)).
- README license audit now notes that `certifi` (transitive) is MPL-2.0 —
  file-level copyleft, compatible with MIT
  ([#5](https://github.com/hieutachi/rosbridge-mcp/issues/5)).

### Security

- Readonly mode (`ROSBRIDGE_MCP_READONLY`) switched from a blocklist to a
  frozen **allowlist** of known read-only `/rosapi` introspection services;
  unknown or future `/rosapi` services are rejected by default
  ([#3](https://github.com/hieutachi/rosbridge-mcp/issues/3)). The new
  `send_action_goal` / `cancel_action_goal` tools are blocked in readonly
  mode; `get_tf_tree` and `get_camera_image` are read-only and allowed.

## [0.1.0] - 2026-08-17

### Added

- Initial release: MCP server bridging AI agents to ROS 2 via the rosbridge
  v2 protocol (WebSocket + JSON).
- 7 tools: `list_topics`, `list_nodes`, `list_services`,
  `get_topic_snapshot`, `publish_message`, `call_service`,
  `get_connection_status`.
- Readonly mode via `ROSBRIDGE_MCP_READONLY`.
- Async rosbridge client with lazy connect, transparent reconnect, and
  correlation ids; in-process mock rosbridge server; 21 tests; CI on
  Python 3.10 and 3.12.
- Per-scenario documentation (Claude Desktop, Cursor/VS Code, simulator
  quickstart, real-robot safety, development), security policy, roadmap,
  and a privacy/legal audit.

[0.2.0]: https://github.com/hieutachi/rosbridge-mcp/releases/tag/v0.2.0
[0.1.0]: https://github.com/hieutachi/rosbridge-mcp/releases/tag/v0.1.0
