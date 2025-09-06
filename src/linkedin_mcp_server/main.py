"""Main module for the LinkedIn MCP server with DXT compatibility."""

import os
import sys
import traceback
from typing import Any, Dict, List, Optional

from loguru import logger
from pathlib import Path

from urllib.parse import quote_plus, quote
from mcp.server.fastmcp import FastMCP

from linkedin_mcp_server.web_scrapper import JobPostingExtractor

# Configure logger for DXT environment
logger.remove()
logger.add(
    sys.stderr, 
    level="INFO",
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    colorize=True
)   
    
# Configure transport and statelessness
trspt = "stdio"
stateless_http = False
match os.environ.get("TRANSPORT", trspt):
    case "sse":
        trspt = "sse"
        stateless_http = False
        logger.warning("SSE transport is deprecated. Using stdio (locally) or streamable-http (remote) instead.")
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


# Initialize FastMCP server with error handling
try:
    host = os.environ.get("HOST", "0.0.0.0")  
    port = int(os.environ.get("PORT", 10000))  
    mcp = FastMCP("linkedin_mcp_fps", stateless_http=stateless_http, host=host, port=port)
    logger.info(f"FastMCP server initialized with transport: {trspt}, host: {host}, port: {port}")
except Exception as e:
    logger.error(f"Failed to initialize FastMCP server: {e}")
    raise

extractor = JobPostingExtractor()

# NOTE: We have to wrap the resources to be accessible from the prompts

@mcp.tool()
def get_url_for_jobs_search(location: str = "San Francisco", distance: int = 25, query: str = "AI Research Engineer") -> str:
    """
    Generates a properly encoded URL that can be used to search for jobs on LinkedIn.
    The generated URL is compatible with LinkedIn's job search API.
    
    Args:
        location: The location to search for jobs in LinkedIn (required)
        distance: The distance from the location to search for jobs in LinkedIn (10, 25, 35, 50, 75, 100)
        query: The search query string for jobs in LinkedIn (required)
               
    Returns:
        str: A properly encoded URL to search for jobs on LinkedIn.
    """
    if not isinstance(distance, int) or distance not in [10, 25, 35, 50, 75, 100]:
        logger.warning(f"Invalid distance {distance}, using default 25")
        distance = 25
        
    logger.info(f"Generating job search URL for location: {location}, distance: {distance}, query: {query}")
    return compose_job_search_url(location, distance, query)

@mcp.resource("linkedinmcpfps://job_search_query/{location}/{distance}/{query}")
def compose_job_search_url(location: str="San Francisco", distance: int=25, query: str="AI Research Engineer") -> str:
    """
    Composes the URL to search for jobs in LinkedIn with proper URI encoding.
    
    Args:
        location: The location to search for jobs in LinkedIn
        distance: The distance from the location to search for jobs in LinkedIn
        query: The search query string for jobs in LinkedIn
        
    Returns:
        str: Properly encoded URL string with a placeholder for the start index.
    """
    encoded_location = quote_plus(location)
    encoded_distance = quote_plus(str(distance))
    encoded_query = quote_plus(query)
    logger.info(f"Encoded query: {encoded_query}")
    # The double curly braces are escaped to produce a single curly brace for later formatting of the start index
    return f"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search-results/?location={encoded_location}&distance={encoded_distance}&keywords={encoded_query}"

@mcp.tool()
def get_new_job_ids(url: str, num_pages: int = 1) -> str:
    """
    Gets the new job ids retrieved from the LinkedIn url passed as a parameter, exploring
    the number of pages specified.
    
    Args:
        url: The URL to search for jobs in LinkedIn (required)
        num_pages: The number of pages to retrieve ids from (1-5 recommended)
        
    Returns:
        str: Comma-separated list of new job IDs retrieved from the explored pages
    """    
    if not isinstance(num_pages, int) or num_pages < 1 or num_pages > 10:
        logger.warning(f"Invalid num_pages {num_pages}, using default 1")
        num_pages = 1
        
    logger.info(f"Fetching job listings from LinkedIn URL: {url[:100]}...")
    
    all_job_ids = extractor.retrieve_job_ids_from_linkedin(base_url=url, max_pages=num_pages)
    new_job_ids = extractor.get_new_job_ids(all_job_ids)
    
    logger.info(f"Found {len(new_job_ids)} new jobs to process")
    
    if not new_job_ids:
        return "No new job IDs found. All jobs may have been previously processed."
    
    return ",".join(new_job_ids)

@mcp.tool()
def get_jobs_raw_metadata(job_ids: List[str]) -> Dict[str, Any]:
    """
    Gets the job raw metadata for the given job IDs passed as parameter.
    
    Args:
        job_ids: List of job IDs to get the job raw metadata for (max 20 jobs recommended)
        
    Returns:
        Dict: Job IDs as keys, and the corresponding job metadata information as values
    """
    if len(job_ids) > 50:
        logger.warning(f"Large number of job IDs ({len(job_ids)}), limiting to first 20")
        job_ids = job_ids[:20]
    
    # Validate individual job IDs
    valid_job_ids = [job_id.strip() for job_id in job_ids if isinstance(job_id, str) and job_id.strip()]
    
    logger.info(f"Retrieving metadata for {len(valid_job_ids)} job IDs")
    
    metadata = extractor.get_jobs_raw_metadata(valid_job_ids)
    logger.info(f"Successfully retrieved metadata for {len(metadata)} jobs")
    return metadata


@mcp.tool()
def adapt_cv_to_latest_job(
    position: str = "Research Engineer or ML Engineer or AI Engineer",
    location: str = "San Francisco",
    job_id: str = "first") -> str:
    """
    Adapts Francisco Perez-Sorrosal's CV to the position of the job description retrieved from LinkedIn 
    for the particular location specified and based on the job id.
    
    Args:
        position: The position to search for jobs for (required)
        location: The location where the job should be located (required)
        job_id: The job id to retrieve the metadata for or "first"/"latest" (required)
        
    Returns:
        str: The job details and the generated adapted CV tailored to the job description
    """
    logger.info(f"Adapting CV for position: {position}, location: {location}, job_id: {job_id}")
    return adapt_cv(position, location, job_id)

@mcp.prompt()
def adapt_cv(
    position: str = "Research Engineer or ML Engineer or AI Engineer",
    location: str = "San Francisco",
    job_id: str = "first"
) -> str:
    """Prompt for getting the latest job generating a summary of Francisco Perez-Sorrosal's CV based on the specified parameters.
    
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
    2. Summarize and adapt Francisco's CV to the job's description retrieved with the most appropriate configuration.
    """


if __name__ == "__main__":
    try:
        # Log environment information for debugging
        logger.info(f"Python version: {sys.version}")
        logger.info(f"Current working directory: {os.getcwd()}")
        logger.info(f"Python path: {sys.path}")
        logger.info(f"Environment variables: TRANSPORT={os.environ.get('TRANSPORT')}, HOST={os.environ.get('HOST')}, PORT={os.environ.get('PORT')}")
        
        # Initialize and run the server with the specified transport
        logger.info(f"Starting LinkedIn MCP server with {trspt} transport ({host}:{port}) and stateless_http={stateless_http}...")
        
        # Additional pre-flight checks
        if trspt == "stdio":
            logger.info("Using stdio transport - suitable for local Claude Desktop integration")
        elif trspt == "streamable-http":
            logger.info(f"Using HTTP transport - server will be accessible at http://{host}:{port}/mcp")
        
        # Start the server
        mcp.run(transport=trspt)
        
    except KeyboardInterrupt:
        logger.info("Server shutdown requested by user")
    except Exception as e:
        logger.error(f"Fatal error starting server: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        sys.exit(1)
