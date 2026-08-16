"""rosbridge-mcp: MCP server bridging AI agents to ROS 2 via rosbridge."""

from rosbridge_mcp.client import RosbridgeClient, RosbridgeError

__version__ = "0.1.0"
__all__ = ["RosbridgeClient", "RosbridgeError", "__version__"]
