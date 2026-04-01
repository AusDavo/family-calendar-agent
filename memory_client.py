import os
import logging

from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

logger = logging.getLogger(__name__)

MEMORY_SERVER_URL = os.environ.get("MEMORY_SERVER_URL", "http://memory-server:8000/mcp/")
MCP_API_KEY = os.environ.get("MCP_API_KEY", "")


def _transport() -> StreamableHttpTransport:
    return StreamableHttpTransport(
        MEMORY_SERVER_URL,
        headers={"Authorization": f"Bearer {MCP_API_KEY}"},
    )


async def store_memory(
    content: str,
    tags: list[str] | None = None,
    metadata: dict | None = None,
) -> str:
    """Store a memory via the MCP memory server."""
    args = {"content": content, "source": "telegram-bot"}
    if tags:
        args["tags"] = tags
    if metadata:
        args["metadata"] = metadata

    try:
        async with Client(transport=_transport()) as client:
            result = await client.call_tool("store_memory", args)
            return result.content[0].text if result.content else '{"status": "stored"}'
    except Exception as e:
        logger.error("Failed to store memory: %s", e)
        return f'{{"status": "error", "message": "{e}"}}'


async def search_memory(
    query: str,
    limit: int = 5,
    tags: list[str] | None = None,
) -> str:
    """Search memories via the MCP memory server."""
    args = {"query": query, "limit": limit}
    if tags:
        args["tags"] = tags

    try:
        async with Client(transport=_transport()) as client:
            result = await client.call_tool("search_memory", args)
            return result.content[0].text if result.content else '{"count": 0, "results": []}'
    except Exception as e:
        logger.error("Failed to search memory: %s", e)
        return f'{{"count": 0, "results": [], "error": "{e}"}}'
