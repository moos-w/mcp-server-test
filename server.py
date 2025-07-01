from __future__ import annotations

import csv
import os
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.routing import Mount, Route
import uvicorn

# Initialize FastMCP server with a generic namespace
mcp = FastMCP("csv")

# Path to the CSV file (can be overridden with the CSV_PATH environment variable)
CSV_PATH = os.getenv("CSV_PATH", "data.csv")


def read_csv_rows() -> list[dict[str, Any]]:
    """Read all rows from the configured CSV file."""
    with open(CSV_PATH, newline="", encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)
        return list(reader)


@mcp.tool()
async def find_rows(column: str, value: str) -> str:
    """Return CSV rows where ``column`` equals ``value``."""
    rows = read_csv_rows()
    matching = [row for row in rows if row.get(column) == value]
    if not matching:
        return "No matching rows found."
    lines = [", ".join(f"{k}={v}" for k, v in row.items()) for row in matching]
    return "\n".join(lines)


def create_starlette_app(mcp_server: Server, *, debug: bool = False) -> Starlette:
    """Create a Starlette application that serves the MCP server with SSE."""
    sse = SseServerTransport("/messages/")

    async def handle_sse(request: Request) -> None:
        async with sse.connect_sse(
            request.scope,
            request.receive,
            request._send,  # noqa: SLF001
        ) as (read_stream, write_stream):
            await mcp_server.run(
                read_stream,
                write_stream,
                mcp_server.create_initialization_options(),
            )

    return Starlette(
        debug=debug,
        routes=[
            Route("/sse", endpoint=handle_sse),
            Mount("/messages/", app=sse.handle_post_message),
        ],
    )


if __name__ == "__main__":
    mcp_server = mcp._mcp_server  # noqa: WPS437

    import argparse

    parser = argparse.ArgumentParser(description="Run MCP server with CSV tools")
    parser.add_argument("--transport", choices=["stdio", "sse"], default="stdio")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()

    if args.transport == "stdio":
        mcp.run(transport="stdio")
    else:
        starlette_app = create_starlette_app(mcp_server, debug=True)
        uvicorn.run(starlette_app, host=args.host, port=args.port)
