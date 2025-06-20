"""Main module for the CV MCP server with Anthropic integration."""

import os

from pathlib import Path

from urllib.parse import quote_plus
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
mcp = FastMCP("linkedin_mcp_server", stateless_http=stateless_http, host=host, port=port)

# NOTE: We have to wrap the resources to be accessible from the prompts


@mcp.tool()
def get_url_for_jobs_search(query: str = "Looking for Research Enginer/Machine Learning/AI Engineer jobs in San Francisco") -> str:
    """
    Gets the URL for the jobs search query from LinkedIn.
    """
    return compose_url_for_jobs_search(query)

@mcp.resource("linkedinmcpfps://job_search_query")
def compose_url_for_jobs_search(query: str) -> str:
    """
    Composes the URL to search for jobs in LinkedIn with proper URI encoding.
    
    Args:
        query: The search query string for jobs in LinkedIn
        
    Returns:
        str: Properly encoded URL string
    """
    final_query = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search-results/?distance=25&geoId=102277331&keywords={query}&start={}".format(query=query)
    return quote_plus(final_query) 

@mcp.tool()
def connect() -> str:
    """Connect to linkedin server."""
    return "Connected to CV MCP server."


if __name__ == "__main__":
    # args: Namespace = parse_cli_arguments()
    
    # Initialize and run the server with the specified transport
    print(f"Starting CV MCP server with {trspt} transport ({host}:{port}) and stateless_http={stateless_http}...")
    mcp.run(transport=trspt)
