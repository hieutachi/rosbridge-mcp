# Roadmap

Where rosbridge-mcp is going, stage by stage. Every item below is technically feasible with the current architecture (rosbridge v2 protocol already supports actions, TF, and binary-safe encodings); what each stage needs is the listed resources. Contributions toward any stage are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).

Status today (v0.1): 7 tools, 21 tests, mock-based CI, per-scenario docs, readonly guardrail. Zero telemetry, MIT licensed.

## v0.2 — Perception & actions (next)

**Goal:** cover the three most-requested robot interactions beyond topics/services.

| Deliverable | Notes |
| --- | --- |
| ROS 2 action client tools (`send_goal`, `get_goal_status`, `cancel_goal`) | rosbridge ≥ 0.12 exposes `send_action_goal` / `cancel_action_goal` ops; same correlation-id pattern as services |
| TF tree snapshot tool (`get_transform`) | subscribe `/tf` + `/tf_static` briefly, or call `/tf2_web_republisher` when present |
| Camera image snapshot (base64 JPEG/PNG, downscaled) | subscribe `sensor_msgs/msg/CompressedImage`; return MCP image content so vision models can see through the robot's camera |
| Topic allow/deny-list env vars | pure policy filter, complements readonly mode |

**Resources needed:** ~3–4 weeks of one developer's part-time effort; a ROS 2 Humble/Jazzy machine or Docker for integration testing (mock covers unit tests); no special hardware.

## v0.3 — Deployment & security hardening

**Goal:** make production deployment one command and add authentication.

| Deliverable | Notes |
| --- | --- |
| Streamable HTTP / SSE transport option | FastMCP already supports it; expose via CLI flag |
| Official Docker image (`ghcr.io`) + compose file bundling rosbridge | CI publish job |
| rosbridge `auth` op support (MAC/token per rosbridge_suite spec) + `wss://` TLS | closes the "no auth by default" gap |
| Structured local logging with redaction options | local only — no telemetry, ever (see Privacy in README) |

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
