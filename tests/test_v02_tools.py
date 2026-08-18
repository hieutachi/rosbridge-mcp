"""Tests for the v0.2 tools: actions, TF tree, and camera snapshot."""

from __future__ import annotations

import base64

import pytest

pytestmark = pytest.mark.asyncio


# --------------------------------------------------------------------- #
# Action client
# --------------------------------------------------------------------- #


async def test_send_action_goal_waits_for_result(tools, mock_rosbridge):
    result = await tools.send_action_goal(
        "/fibonacci", "test_msgs/action/Fibonacci", {"order": 5}, timeout=5.0
    )
    assert result["success"] is True
    assert result["status"] == 4
    assert result["status_text"] == "succeeded"
    assert result["values"]["echo_goal"] == {"order": 5}
    assert result["last_feedback"] == {"progress": 0.9}
    sent = mock_rosbridge.action_goals[-1]
    assert sent["action"] == "/fibonacci"
    assert sent["action_type"] == "test_msgs/action/Fibonacci"
    assert sent["args"] == {"order": 5}


async def test_send_action_goal_no_wait_returns_goal_id(tools, mock_rosbridge):
    result = await tools.send_action_goal(
        "/slow_move", "test_msgs/action/Slow", {}, wait_for_result=False
    )
    assert result["result_pending"] is True
    assert result["goal_id"]
    assert mock_rosbridge.action_goals[-1]["id"] == result["goal_id"]


async def test_cancel_action_goal(tools, mock_rosbridge):
    started = await tools.send_action_goal(
        "/slow_move", "test_msgs/action/Slow", {}, wait_for_result=False
    )
    result = await tools.cancel_action_goal("/slow_move", started["goal_id"])
    assert result["cancel_sent"] is True
    cancelled = mock_rosbridge.cancelled_goals[-1]
    assert cancelled["id"] == started["goal_id"]
    assert cancelled["action"] == "/slow_move"


async def test_send_action_goal_old_rosbridge_guidance(tools, mock_rosbridge):
    mock_rosbridge.supports_actions = False
    result = await tools.send_action_goal(
        "/fibonacci", "test_msgs/action/Fibonacci", {}, timeout=5.0
    )
    assert result["success"] is False
    assert "rosbridge_suite" in result["error"]


async def test_readonly_blocks_send_action_goal(tools, monkeypatch):
    monkeypatch.setenv("ROSBRIDGE_MCP_READONLY", "1")
    result = await tools.send_action_goal("/nav", "nav2_msgs/action/NavigateToPose", {})
    assert result["readonly"] is True
    assert "Rejected" in result["error"]


async def test_readonly_blocks_cancel_action_goal(tools, monkeypatch):
    monkeypatch.setenv("ROSBRIDGE_MCP_READONLY", "1")
    result = await tools.cancel_action_goal("/nav", "send_action_goal:1")
    assert result["readonly"] is True


# --------------------------------------------------------------------- #
# TF tree
# --------------------------------------------------------------------- #


async def test_get_tf_tree_merges_static_and_dynamic(tools):
    result = await tools.get_tf_tree(timeout=0.4)
    frames = result["frames"]
    assert result["frame_count"] == 2
    assert frames["base_link"]["parent"] == "odom"
    assert frames["base_link"]["source"] == "dynamic"
    assert frames["base_link"]["translation"]["x"] == 1.0
    assert frames["laser"]["parent"] == "base_link"
    assert frames["laser"]["source"] == "static"
    assert result["tree"]["odom"] == ["base_link"]
    assert result["tree"]["base_link"] == ["laser"]
    assert result["roots"] == ["odom"]


async def test_get_tf_tree_allowed_in_readonly(tools, monkeypatch):
    monkeypatch.setenv("ROSBRIDGE_MCP_READONLY", "1")
    result = await tools.get_tf_tree(timeout=0.4)
    assert result["frame_count"] == 2


async def test_get_tf_tree_clamps_timeout(tools):
    result = await tools.get_tf_tree(timeout=0.01)
    assert result["listened_s"] == 0.2


# --------------------------------------------------------------------- #
# Camera snapshot
# --------------------------------------------------------------------- #


async def test_get_camera_image_compressed(tools):
    from rosbridge_mcp.mock_server import FAKE_JPEG

    result = await tools.get_camera_image("/camera/image/compressed", timeout=2.0)
    assert result["format"] == "jpeg"
    assert result["size_bytes"] == len(FAKE_JPEG)
    assert base64.b64decode(result["data_base64"]).startswith(b"\xff\xd8\xff")


async def test_get_camera_image_raw(tools):
    result = await tools.get_camera_image("/camera/image_raw", timeout=2.0)
    assert result["format"] == "raw (rgb8)"
    assert result["width"] == 2
    assert result["height"] == 2
    assert result["size_bytes"] == 12
    assert base64.b64decode(result["data_base64"]) == b"\x01" * 12


async def test_get_camera_image_too_large_suggests_compressed(tools):
    result = await tools.get_camera_image("/camera/huge_raw", timeout=5.0)
    assert "data_base64" not in result
    assert result["size_bytes"] > 4 * 1024 * 1024
    assert "CompressedImage" in result["error"]
    assert result["width"] == 1183  # metadata still reported


async def test_get_camera_image_silent_topic(tools):
    result = await tools.get_camera_image("/no_such_camera", timeout=0.3)
    assert result["timed_out"] is True
    assert "No image received" in result["error"]


async def test_get_camera_image_allowed_in_readonly(tools, monkeypatch):
    monkeypatch.setenv("ROSBRIDGE_MCP_READONLY", "1")
    result = await tools.get_camera_image("/camera/image/compressed", timeout=2.0)
    assert result["format"] == "jpeg"
