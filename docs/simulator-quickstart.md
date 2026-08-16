# No robot? Try rosbridge-mcp with Docker or a simulator

Three ways to get a live rosbridge endpoint at `ws://localhost:9090` without owning a robot, from lightest to most realistic. Each option is independent — pick one.

## Option A — Bundled mock server (no Docker, no ROS, 10 seconds)

The package ships a fake rosbridge with canned topics (`/chatter`, `/cmd_vel`, `/scan`) and rosapi services:

```bash
pip install rosbridge-mcp
python -m rosbridge_mcp.mock_server 9090
```

Leave it running, configure your MCP client with `ROSBRIDGE_URL=ws://localhost:9090` ([Claude Desktop guide](claude-desktop.md), [Cursor/VS Code guide](cursor-vscode.md)), and you can exercise every tool. Good for testing the wiring; the data is fake.

## Option B — Real ROS 2 in Docker (no ROS install, ~5 minutes)

Requires [Docker](https://docs.docker.com/get-docker/). This runs a genuine ROS 2 Humble system with a real rosbridge:

```bash
docker run -it --rm --name ros-bridge -p 9090:9090 ros:humble bash -c "\
  apt-get update && apt-get install -y ros-humble-rosbridge-suite && \
  . /opt/ros/humble/setup.sh && \
  ros2 launch rosbridge_server rosbridge_websocket_launch.xml"
```

Wait for `Rosbridge WebSocket server started on port 9090`. Then, in a second terminal, add a node that actually publishes something:

```bash
docker exec -it ros-bridge bash -c "\
  . /opt/ros/humble/setup.sh && ros2 run demo_nodes_cpp talker"
```

Now `ws://localhost:9090` is a real rosbridge. Ask your agent to `list_topics` (you'll see `/chatter`), snapshot `/chatter`, or publish to a new topic and read it back with `docker exec ... ros2 topic echo`.

Tip: to avoid reinstalling rosbridge every run, commit the container once: `docker commit ros-bridge ros-humble-rosbridge`, then start it later with `docker run -it --rm -p 9090:9090 ros-humble-rosbridge bash -c ". /opt/ros/humble/setup.sh && ros2 launch rosbridge_server rosbridge_websocket_launch.xml"`.

## Option C — TurtleBot3 in Gazebo (full robot simulation)

Requires a Ubuntu machine (or VM) with ROS 2 Humble installed. This gives you a simulated robot with `/scan`, `/odom`, `/cmd_vel` — the closest thing to real hardware:

```bash
sudo apt install ros-humble-turtlebot3-gazebo ros-humble-rosbridge-suite

# Terminal 1: simulated world + robot
export TURTLEBOT3_MODEL=burger
ros2 launch turtlebot3_gazebo turtlebot3_world.launch.py

# Terminal 2: rosbridge
ros2 launch rosbridge_server rosbridge_websocket_launch.xml
```

Point `ROSBRIDGE_URL` at `ws://<ubuntu-machine-ip>:9090` (or `ws://localhost:9090` if the MCP client runs on the same machine). Now you can run the full loop safely:

1. `get_topic_snapshot` on `/scan` — the agent sees the simulated laser.
2. `get_topic_snapshot` on `/odom` — where the robot is.
3. `publish_message` to `/cmd_vel` with a small `linear.x` — the robot moves in Gazebo.
4. Publish zero velocity to stop.

This is the recommended rehearsal before trying a [real robot](real-robot-safety.md).

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `Cannot connect to rosbridge at ws://localhost:9090` | The server isn't running or the port isn't mapped. For Docker, confirm `-p 9090:9090` is in the run command and the launch log says the server started. |
| Docker: `port is already allocated` | Something else uses 9090. Map another port (`-p 9091:9090`) and set `ROSBRIDGE_URL=ws://localhost:9091`. |
| `list_topics` works but snapshots return `timed_out: true` | Nothing is publishing on that topic. In Option B, start the `talker`; in Gazebo, check the simulation is not paused. |
| Service calls hang/time out | `rosapi` node missing — always use `rosbridge_websocket_launch.xml`, which includes it. |
| Gazebo topics missing | `TURTLEBOT3_MODEL` not exported in that terminal, or Gazebo still loading (first start downloads models and can take minutes). |
| Firewall (remote host) | Allow inbound TCP 9090 on the ROS machine: `sudo ufw allow 9090/tcp`. |
