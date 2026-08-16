# Connecting a real robot — safety checklist

An LLM with publish access to `/cmd_vel` can move a physical machine. Work through this checklist in order; do not skip ahead to write access.

## Prerequisites

- A robot running ROS 2 with `rosbridge_server` installed (`sudo apt install ros-$ROS_DISTRO-rosbridge-suite`)
- You know how to physically stop the robot (e-stop, kill switch, lifting drive wheels off the ground)
- Ideally: you have rehearsed the same workflow [in simulation](simulator-quickstart.md) first

## Step 1 — Start rosbridge on the robot

```bash
ros2 launch rosbridge_server rosbridge_websocket_launch.xml
```

By default this listens on `0.0.0.0:9090` **without authentication** — anyone who can reach that port can control the robot. Mitigate:

- Keep robot and workstation on a trusted/isolated network (lab VLAN, direct link, or VPN such as WireGuard/Tailscale). Do not expose 9090 to the internet.
- Restrict with a firewall to your workstation's IP: `sudo ufw allow from <workstation-ip> to any port 9090 proto tcp` and `sudo ufw deny 9090/tcp` for everyone else.

## Step 2 — Connect in read-only mode first

Configure your MCP client ([Claude Desktop](claude-desktop.md) / [Cursor & VS Code](cursor-vscode.md)) with:

```json
"env": {
  "ROSBRIDGE_URL": "ws://<robot-ip>:9090",
  "ROSBRIDGE_MCP_READONLY": "true"
}
```

In read-only mode the agent can list topics/nodes/services and snapshot any topic, but `publish_message` is rejected and `call_service` only allows read-only `/rosapi/*` introspection.

## Step 3 — Understand the robot before writing to it

With the agent (still read-only), build a picture:

1. `list_topics` — identify sensor topics (`/scan`, `/odom`, `/camera/...`, battery) and command topics (`/cmd_vel`, arm/gripper controllers).
2. `get_topic_snapshot` on `/odom` — confirm the pose makes sense and updates.
3. `get_topic_snapshot` on `/scan` — confirm obstacle data is live and sane.
4. Ask the agent to explain what each command topic does and what a *safe minimal* message for it looks like — verify against your robot's documentation. Know your robot's velocity limits before publishing any.

## Step 4 — Enable writes deliberately

Only now set `ROSBRIDGE_MCP_READONLY` to `"false"` and restart the MCP client. First writes should be minimal and reversible:

- Publish a **zero** velocity to `/cmd_vel` — nothing should move; this proves the pipeline without risk.
- Then a very small velocity (e.g. `linear.x = 0.05`) for one message, hands on the e-stop.
- Prefer prompting patterns where the agent reads `/scan`/`/odom` **before every** motion command and explains its intent first.
- When done, turn read-only back on. Treat write access like sudo: enable for the session that needs it, not permanently.

## Emergency stop

- Physical e-stop is the only real safety mechanism. Software stop: publish an all-zero `geometry_msgs/msg/Twist` to `/cmd_vel`.
- Killing the MCP server or rosbridge stops *new* commands, but many robot bases keep executing the last velocity until a timeout — check your base's `cmd_vel` timeout behavior.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `Cannot connect to rosbridge at ws://<robot-ip>:9090` | rosbridge not running on the robot, wrong IP, or firewall. From the workstation: `ping <robot-ip>`, then check the port is open (`Test-NetConnection <robot-ip> -Port 9090` on Windows, `nc -zv <robot-ip> 9090` on Linux/macOS). |
| Connects, but topics list is empty / stale | rosbridge and robot nodes on different `ROS_DOMAIN_ID`s. Launch rosbridge in the same environment as the robot's stack. |
| `publish_message` rejected | Read-only mode is on (by design). Flip `ROSBRIDGE_MCP_READONLY` when Step 4 applies. |
| Robot ignores `/cmd_vel` publishes | Wrong `msg_type` (ROS 2 needs `geometry_msgs/msg/Twist`, with `/msg/`), a mux/safety controller overrides the topic, or the base expects `TwistStamped`. `ros2 topic info /cmd_vel` on the robot shows the expected type. |
| Robot keeps moving after a command | The base latches the last velocity. Publish zero velocity immediately; investigate the base's velocity timeout setting. |
