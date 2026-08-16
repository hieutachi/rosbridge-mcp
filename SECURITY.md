# Security Policy

## Reporting a vulnerability

Please report security issues **privately** via GitHub's *Security → Report a vulnerability* (private vulnerability reporting) on this repository, or by opening a minimal issue asking for a private contact channel — do not post exploit details publicly. You can expect an acknowledgement within 7 days. Please include reproduction steps and the affected version.

Supported versions: only the latest released version receives security fixes.

## Deployment security model

Understand what this software does and does not protect:

- **rosbridge has no authentication by default.** `rosbridge_server` listens on `0.0.0.0:9090` and anyone who can reach that port can control the robot — with or without this project. Never expose rosbridge to the public internet. Keep it on an isolated/trusted network (lab VLAN, VPN such as WireGuard/Tailscale) and firewall the port to known client IPs.
- **This server is a client of rosbridge**, connecting only to the `ROSBRIDGE_URL` you configure. It adds one guardrail on top: `ROSBRIDGE_MCP_READONLY=true` rejects `publish_message` and non-introspection `call_service` requests. This is a policy filter inside this process, **not** a substitute for network security — a hostile actor on the network can still talk to rosbridge directly.
- **The MCP client (LLM) decides which tools to call.** Treat write access like sudo: enable it only for sessions that need it, and keep a physical e-stop within reach when real hardware is involved. See [docs/real-robot-safety.md](docs/real-robot-safety.md).

## Disclaimer of liability

This software is provided **"AS IS"**, without warranty of any kind, under the [MIT License](LICENSE). Operating a physical robot through this software is done entirely at the operator's risk. The authors and contributors accept no responsibility for damage to hardware, property, or persons resulting from commands issued through this bridge — the person who enables write access and connects a robot is the responsible operator.
