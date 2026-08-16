"""Demo: exercise RosbridgeClient against the bundled mock rosbridge server.

No ROS required. Run: ``python examples/demo.py``
"""

import asyncio
import json

from rosbridge_mcp.client import RosbridgeClient
from rosbridge_mcp.mock_server import MockRosbridge


async def main() -> None:
    mock = MockRosbridge()
    await mock.start()
    print(f"Mock rosbridge running at {mock.url}\n")

    client = RosbridgeClient(url=mock.url)
    try:
        topics = await client.call_service("/rosapi/topics")
        print("Topics:", json.dumps(topics, indent=2))

        snapshot = await client.collect_messages("/chatter", count=1, timeout=2.0)
        print("\nSnapshot of /chatter:", snapshot)

        await client.publish(
            "/cmd_vel",
            "geometry_msgs/msg/Twist",
            {"linear": {"x": 0.1, "y": 0.0, "z": 0.0}, "angular": {"z": 0.2}},
        )
        await asyncio.sleep(0.1)
        print("\nMock recorded publish:", mock.published[-1])

        print("\nConnection status:", json.dumps(client.status(), indent=2))
    finally:
        await client.close()
        await mock.stop()


if __name__ == "__main__":
    asyncio.run(main())
