# Roadmap

Where rosbridge-mcp is going, stage by stage. Every item below is technically feasible with the current architecture (rosbridge v2 protocol already supports actions, TF, and binary-safe encodings); what each stage needs is the listed resources. Contributions toward any stage are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).

Status today (v0.2.0): 11 tools (topics, services, ROS 2 actions, TF tree, camera snapshots), 43 tests, mock-based CI, per-scenario docs, readonly guardrail with a `/rosapi` allowlist. Zero telemetry, MIT licensed.

## v0.2 — Perception & actions — **Done in v0.2.0**

**Goal:** cover the three most-requested robot interactions beyond topics/services.

| Deliverable | Status |
| --- | --- |
| ROS 2 action client tools | ✅ Done in v0.2.0 as `send_action_goal` (send + wait for result + last feedback, or fire-and-forget with a returned `goal_id`) and `cancel_action_goal`, using the rosbridge `send_action_goal` / `cancel_action_goal` ops with the same correlation-id pattern as services. A separate `get_goal_status` tool was not needed: the result carries the final `action_msgs/GoalStatus`. |
| TF tree snapshot tool | ✅ Done in v0.2.0 as `get_tf_tree`: subscribes `/tf` + `/tf_static` briefly and merges transforms into a parent→child tree with static/dynamic provenance. |
| Camera image snapshot | ✅ Done in v0.2.0 as `get_camera_image`: one `CompressedImage` (or raw `Image`) frame as base64, 4 MB safety limit. Returned as JSON base64 rather than MCP image content for now. |
| Topic allow/deny-list env vars | ⏭️ Moved to v0.3 (fits the security-hardening theme; readonly mode gained a `/rosapi` service allowlist in v0.2.0 instead). |

## v0.3 — Deployment & security hardening

**Goal:** make production deployment one command and add authentication.

| Deliverable | Notes |
| --- | --- |
| Streamable HTTP / SSE transport option | FastMCP already supports it; expose via CLI flag |
| Official Docker image (`ghcr.io`) + compose file bundling rosbridge | CI publish job |
| rosbridge `auth` op support (MAC/token per rosbridge_suite spec) + `wss://` TLS | closes the "no auth by default" gap |
| Structured local logging with redaction options | local only — no telemetry, ever (see Privacy in README) |
| Topic allow/deny-list env vars | pure policy filter, complements readonly mode (moved from v0.2) |

**Resources needed:** ~4 weeks part-time dev; a small cloud VM or self-hosted runner for image builds and network testing; a security-minded reviewer for the auth layer (looking for a contributor here).

## v0.4 — Fleet & rich context

**Goal:** from "one robot" to "the robot lab".

| Deliverable | Notes |
| --- | --- |
| Multi-robot support: named connections to several rosbridge endpoints, per-robot readonly policy | `RosbridgeClient` is already instance-scoped; needs a registry + tool namespace design |
| MCP resources: URDF, occupancy-grid map, node graph as browsable resources | rosapi + map_server provide the data |
| Latched-topic and parameter browsing | quality-of-life for debugging sessions |

**Resources needed:** ~6 weeks part-time dev; access to 2+ simultaneously running robots or simulator instances (Gazebo multi-robot world is sufficient — no hardware purchase required); design feedback from a real robotics lab (looking for an academic/industrial pilot partner).

## v1.0 — Stability & ecosystem

**Goal:** a dependable default choice for AI-agent ↔ ROS bridging.

| Deliverable | Notes |
| --- | --- |
| Frozen, semver-guaranteed tool API | after v0.2–v0.4 shake out the shapes |
| Listing in the official MCP registry + Claude/Cursor directories | packaging + review effort |
| End-to-end tested examples: TurtleBot3 Gazebo and NVIDIA Isaac Sim | Isaac Sim needs an RTX-class GPU (~one workstation) — the main hardware ask of the whole roadmap |
| Hardware-in-the-loop CI (self-hosted runner + a low-cost robot, e.g. TurtleBot or Unitree Go2) | stretch goal; needs sponsored hardware (~$1–3k) or a lab partnership |

**Resources needed:** sustained maintainer time (~2 days/week for a quarter), 1 GPU workstation for Isaac Sim validation, optionally one physical robot for HIL CI, and 2–3 regular contributors/reviewers.

## How to help

- **Developers:** pick any deliverable above and open an issue to claim it — [docs/development.md](docs/development.md) explains the codebase in 10 minutes.
- **Labs / companies:** simulator time, robot access, or a GPU workstation directly unblock v0.4/v1.0 items.
- **Users:** issue reports with your ROS distro + rosbridge version are the cheapest way to improve compatibility.
