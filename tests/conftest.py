from __future__ import annotations

import pytest_asyncio

import rosbridge_mcp.server as server
from rosbridge_mcp.client import RosbridgeClient
from rosbridge_mcp.mock_server import MockRosbridge


@pytest_asyncio.fixture
async def mock_rosbridge():
    mock = MockRosbridge()
    await mock.start()
    yield mock
    await mock.stop()


@pytest_asyncio.fixture
async def client(mock_rosbridge):
    client = RosbridgeClient(url=mock_rosbridge.url)
    yield client
    await client.close()


@pytest_asyncio.fixture
async def tools(mock_rosbridge, client, monkeypatch):
    """Wire the server module's shared client to the mock rosbridge."""
    monkeypatch.setattr(server, "_client", client)
    monkeypatch.delenv("ROSBRIDGE_MCP_READONLY", raising=False)
    yield server
