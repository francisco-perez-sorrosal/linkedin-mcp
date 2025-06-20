"""Main module for the CV MCP server with Anthropic integration."""

import os
from typing import Any, Dict, List

from loguru import logger
from pathlib import Path

from urllib.parse import quote_plus, quote
from mcp.server.fastmcp import FastMCP
from linkedin_mcp_server.web_scrapper import JobPostingExtractor

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

extractor = JobPostingExtractor()

@mcp.tool()
def get_url_for_jobs_search(query: str = "Looking for Research Enginer/Machine Learning/AI Engineer jobs in San Francisco") -> str:
    """
    Gets the URL for the jobs search query from LinkedIn.
    """
    return compose_url_for_jobs_search(query)

@mcp.resource("linkedinmcpfps://job_search_query/{query}")
def compose_url_for_jobs_search(query: str) -> str:
    """
    Composes the URL to search for jobs in LinkedIn with proper URI encoding.
    
    Args:
        query: The search query string for jobs in LinkedIn
        
    Returns:
        str: Properly encoded URL string with a placeholder for the start index.
    """
    encoded_query = quote_plus(query)
    logger.info(f"Encoded query: {encoded_query}")
    # The double curly braces are escaped to produce a single curly brace for later formatting of the start index
    return f"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search-results/?distance=25&geoId=102277331&keywords={encoded_query}"

@mcp.tool()
def get_new_job_ids(url: str, num_pages: int = 1) -> List[str]:
    """
    Gets the new job IDs from LinkedIn.
    
    Args:
        url: The URL to search for jobs in LinkedIn
        num_pages: The number of pages to scrape
        
    Returns:
        List of new job IDs
    """
    logger.info("Fetching job listings from LinkedIn...")
    all_job_ids = extractor.retrieve_job_ids_from_linkedin(base_url=url, max_pages=num_pages)
    new_job_ids = extractor.get_new_job_ids(all_job_ids)
    print(f"Found {len(new_job_ids)} new jobs to process")
    return new_job_ids

@mcp.tool()
def get_jobs_raw_metadata(job_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    """
    Gets the job raw metadata for the given job IDs.
    
    Args:
        job_ids: List of job IDs to get the job raw metadata for
        
    Returns:
        Dict of job IDs and their corresponding raw metadata
    """
    return extractor.get_jobs_raw_metadata(job_ids)


if __name__ == "__main__":
    # args: Namespace = parse_cli_arguments()
    
    # Initialize and run the server with the specified transport
    print(f"Starting Linkedin MCP server with {trspt} transport ({host}:{port}) and stateless_http={stateless_http}...")
    mcp.run(transport=trspt)
