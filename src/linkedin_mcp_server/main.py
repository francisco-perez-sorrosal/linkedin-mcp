"""Main module for the CV MCP server with Anthropic integration."""

import os

from pathlib import Path
# from argparse import ArgumentParser, Namespace

import pymupdf4llm
from mcp.server.fastmcp import FastMCP


# Configure transport and statelessness
trspt = "stdio"
stateless_http = False
match os.environ.get("TRANSPORT", "stdio"):
    case "stdio":
        trspt = "stdio"
        stateless_http = False
    case "sse":
        trspt = "sse"
        stateless_http = False
    case "streamable-http":
        trspt = "streamable-http"
        stateless_http = True
    case _:
        trspt = "stdio"
        stateless_http = False


def find_project_root():
    current = Path(__file__).resolve()
    while current != current.parent:
        if (current / 'pyproject.toml').exists():
            return current
        current = current.parent
    return current

PROJECT_ROOT = find_project_root()


# Initialize FastMCP server
host = os.environ.get("HOST", "0.0.0.0")  # render.com needs '0.0.0.0' specified as host when deploying the service
port = int(os.environ.get("PORT", 10000))  # render.com has '10000' as default port
mcp = FastMCP("cv_francisco_perez_sorrosal", stateless_http=stateless_http, host=host, port=port)

# NOTE: We have to wrap the resources to be accessible from the prompts

@mcp.tool()
def connect() -> str:
    """Connect to linkedin server."""
    return "Connected to CV MCP server."


if __name__ == "__main__":
    # args: Namespace = parse_cli_arguments()
    
    # Initialize and run the server with the specified transport
    print(f"Starting CV MCP server with {trspt} transport ({host}:{port}) and stateless_http={stateless_http}...")
    mcp.run(transport=trspt) #, mount_path="/cv")
