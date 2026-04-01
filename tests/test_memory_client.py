"""Tests for memory_client — verifies MCP client integration works correctly."""

import json
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from mcp.types import CallToolResult, TextContent


def _make_call_tool_result(text: str) -> CallToolResult:
    """Build a real CallToolResult like fastmcp returns."""
    return CallToolResult(
        content=[TextContent(type="text", text=text)],
        isError=False,
    )


def _make_empty_result() -> CallToolResult:
    return CallToolResult(content=[], isError=False)


@pytest.mark.asyncio
async def test_store_memory_parses_result():
    """store_memory should return the text from CallToolResult.content[0].text."""
    expected = json.dumps({"status": "stored", "id": "abc-123"})
    mock_result = _make_call_tool_result(expected)

    mock_client = AsyncMock()
    mock_client.call_tool = AsyncMock(return_value=mock_result)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("memory_client.Client", return_value=mock_client):
        from memory_client import store_memory
        result = await store_memory("test content", tags=["test"])

    assert result == expected
    mock_client.call_tool.assert_called_once_with(
        "store_memory",
        {"content": "test content", "source": "telegram-bot", "tags": ["test"]},
    )


@pytest.mark.asyncio
async def test_store_memory_empty_result():
    """store_memory should handle empty content list gracefully."""
    mock_result = _make_empty_result()

    mock_client = AsyncMock()
    mock_client.call_tool = AsyncMock(return_value=mock_result)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("memory_client.Client", return_value=mock_client):
        from memory_client import store_memory
        result = await store_memory("test content")

    assert json.loads(result)["status"] == "stored"


@pytest.mark.asyncio
async def test_search_memory_parses_result():
    """search_memory should return the text from CallToolResult.content[0].text."""
    expected = json.dumps({"count": 1, "results": [{"content": "hello"}]})
    mock_result = _make_call_tool_result(expected)

    mock_client = AsyncMock()
    mock_client.call_tool = AsyncMock(return_value=mock_result)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("memory_client.Client", return_value=mock_client):
        from memory_client import search_memory
        result = await search_memory("hello", limit=3)

    assert result == expected
    mock_client.call_tool.assert_called_once_with(
        "search_memory",
        {"query": "hello", "limit": 3},
    )


@pytest.mark.asyncio
async def test_store_memory_handles_exception():
    """store_memory should not raise on connection errors, return error JSON."""
    mock_client = AsyncMock()
    mock_client.call_tool = AsyncMock(side_effect=ConnectionError("refused"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("memory_client.Client", return_value=mock_client):
        from memory_client import store_memory
        result = await store_memory("test")

    assert "error" in result


@pytest.mark.asyncio
async def test_search_memory_handles_exception():
    """search_memory should not raise on connection errors, return empty results."""
    mock_client = AsyncMock()
    mock_client.call_tool = AsyncMock(side_effect=ConnectionError("refused"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("memory_client.Client", return_value=mock_client):
        from memory_client import search_memory
        result = await search_memory("test")

    parsed = json.loads(result)
    assert parsed["count"] == 0
