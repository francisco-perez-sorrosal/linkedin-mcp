"""Main module for the CV MCP server with Anthropic integration."""

import os
from typing import Any, Dict, List

from loguru import logger
from pathlib import Path

from urllib.parse import quote_plus, quote
from mcp.server.fastmcp import FastMCP

try:
    from linkedin_mcp_server.web_scrapper import JobPostingExtractor
except ImportError:
    logger.info("Failed to import JobPostingExtractor from linkedin_mcp_server.web_scrapper")
    try:
        from .web_scrapper import JobPostingExtractor
    except ImportError:
        logger.info("Failed to import JobPostingExtractor from .web_scrapper")
        try:
            from web_scrapper import JobPostingExtractor
        except ImportError as e:
            logger.info("Failed to import JobPostingExtractor from web_scrapper. :(((((((((")
            raise e
    
    
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

extractor = JobPostingExtractor()
logger.info(f"JobPostingExtractor initialized!")

# NOTE: We have to wrap the resources to be accessible from the prompts

@mcp.tool()
def get_url_for_jobs_search(query: str = "Looking for Research Enginer/Machine Learning/AI Engineer jobs in San Francisco") -> str:
    """
    Generates a properly encoded URL that can be used to search for jobs on LinkedIn.
    The generated URL is compatible with LinkedIn's job search API.
    
    Args:
        query: The search query string for jobs in LinkedIn.
               
    Returns:
        str: A properly encoded URL to search for jobs on LinkedIn.
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
    Gets the new job ids retrieved from the LinkedIn url passed as a parameter, exploring
    the number of pages specified.
    
    Args:
        url: The URL to search for jobs in LinkedIn
        num_pages: The number of pages to retrieve ids from
        
    Returns:
        A list with the new job IDs retrieved from the explored pages from the URL
    """
    logger.info("Fetching job listings from LinkedIn...")
    all_job_ids = extractor.retrieve_job_ids_from_linkedin(base_url=url, max_pages=num_pages)
    new_job_ids = extractor.get_new_job_ids(all_job_ids)
    print(f"Found {len(new_job_ids)} new jobs to process")
    return new_job_ids

@mcp.tool()
def get_jobs_raw_metadata(job_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    """
    Gets the job raw metadata for the given job IDs passed as parameter.
    
    Args:
        job_ids: List of job IDs to get the job raw metadata for
        
    Returns:
        Dict job ids as keys, and the corresponding job metadata information 
        as values (encoded also as a dictonary)
    """
    return extractor.get_jobs_raw_metadata(job_ids)


@mcp.tool()
def adapt_cv_to_latest_job(
    position: str = "Research Engineer or ML Engineer or AI Engineer",
    location: str = "San Francisco",
    job_id: str = "first") -> str:
    """
    Adapts Francisco Perez-Sorrosal's CV to the position of the job description retrieved from linkedin 
    for the particular location specified and based on the job id.
    
    Args:
        position: The position to search for jobs for
        location: The location where the job should be located
        job_id: The job id to retrieve the metadata for
        
    Returns:
        str: The job details and the generated adapted CV tailored to the job description
    """
    return adapt_cv(position, location, job_id)

@mcp.prompt()
def adapt_cv(
    position: str = "Research Engineer or ML Engineer or AI Engineer",
    location: str = "San Francisco",
    job_id: str = "first"
) -> str:
    """Prompt for getting the latest jobgenerating a summary of Francisco Perez-Sorrosal's CV based on the specified parameters.
    
    Args:
        position: The position to search for jobs for
        location: The location to search for jobs for
        job_id: The job id to retrieve the metadata for
        
    Returns:
        str: The job details and the generated adapted CV tailored to the job description
    """
    return f"""
    You are an expert writer and recruiter specialized in technical positions for the area of computer science and
    machine learning and artificial intelligence.
    
    Get a list of new jobs from linkedin (1 page) for a {position} in {location}. Then,take the {job_id} job id from that list, 
    retrieve its metadata. After this, retrieve Francisco's CV. With those contexts, generate these two outputs:
    1. Show the content of the job metadata retreieved properly including it's URL
    2. Adapt and summarize Francisco's CV to the job's description retrieved with the most appropriate configuration.
    """


if __name__ == "__main__":
    # Initialize and run the server with the specified transport
    print(f"Starting Linkedin MCP server with {trspt} transport ({host}:{port}) and stateless_http={stateless_http}...")
    mcp.run(transport=trspt)
