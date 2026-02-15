"""Main module for the LinkedIn MCP server with DXT compatibility."""

import asyncio
import os
import sys
import traceback
from dataclasses import asdict
from typing import Any
from urllib.parse import quote_plus

from loguru import logger
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.prompts import base
from pathlib import Path

from linkedin_mcp_server.cache import BasicInMemoryCache
from linkedin_mcp_server.scraper import (
    JobDetail,
    JobSummary,
    create_client,
    fetch_job_details,
    search_jobs_pages,
)
from linkedin_mcp_server.utils import PromptLoadError, load_prompt_from_yaml

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

# Initialize cache
cache = BasicInMemoryCache(
    app_name="linkedin-mcp",
    cache_subdir="raw_job_description_cache",
    cache_file="raw_job_descriptions.jsonl",
    cache_key_name="job_id",
)


@mcp.tool()
async def search_jobs(
    query: str = "AI Engineer or ML Engineer",
    location: str = "San Francisco",
    distance: int = 25,
    num_pages: int = 1,
    experience_level: str | None = None,
    job_type: str | None = None,
    work_arrangement: str | None = None,
    time_posted: str | None = None,
) -> list[dict[str, str]]:
    """
    Search LinkedIn jobs and return summary data from search result cards.

    Args:
        query: Job title or keywords (default: "AI Engineer or ML Engineer")
        location: City or region (default: "San Francisco")
        distance: Search radius in miles (default: 25; valid: 10, 25, 35, 50, 75, 100)
        num_pages: Number of result pages to scan (default: 1; max: 10)
        experience_level: Experience level filter (1-6: Intern to Executive)
        job_type: Job type filter (F/P/C/T/V/I/O: Full-time, Part-time, Contract, etc.)
        work_arrangement: Work arrangement (1/2/3: On-site, Remote, Hybrid)
        time_posted: Time posted filter (r86400/r604800/r2592000: 24h, 1week, 1month)

    Returns:
        List of job summaries with title, company, location, date, URL, job_id
    """
    # Validate distance
    if distance not in [10, 25, 35, 50, 75, 100]:
        logger.warning(f"Invalid distance {distance}, using default 25")
        distance = 25

    # Validate num_pages
    if num_pages < 1 or num_pages > 10:
        logger.warning(f"Invalid num_pages {num_pages}, using default 1")
        num_pages = 1

    # Build filters dict
    filters = {}
    if experience_level:
        filters["f_E"] = experience_level
    if job_type:
        filters["f_JT"] = job_type
    if work_arrangement:
        filters["f_WT"] = work_arrangement
    if time_posted:
        filters["f_TPR"] = time_posted

    logger.info(f"Searching for '{query}' in {location} ({distance} miles, {num_pages} pages)")

    async with create_client() as client:
        summaries = await search_jobs_pages(client, query, location, distance, num_pages, filters)

    logger.info(f"Found {len(summaries)} job summaries")
    return [asdict(s) for s in summaries]


@mcp.tool()
async def get_job_details(job_ids: list[str]) -> dict[str, dict[str, Any]]:
    """
    Fetch full metadata for specific job IDs. Returns cached data when available, scrapes otherwise.

    Args:
        job_ids: List of LinkedIn job IDs (max 50, truncated to 20 with warning)

    Returns:
        Dict mapping job_id to full metadata (title, company, location, description, etc.)
    """
    if len(job_ids) > 50:
        logger.warning(f"Large number of job IDs ({len(job_ids)}), limiting to first 20")
        job_ids = job_ids[:20]

    # Validate and clean job IDs
    valid_job_ids = [job_id.strip() for job_id in job_ids if isinstance(job_id, str) and job_id.strip()]

    logger.info(f"Retrieving metadata for {len(valid_job_ids)} job IDs")

    # Partition into cached and uncached
    cached_ids = [jid for jid in valid_job_ids if cache.exists(jid)]
    uncached_ids = [jid for jid in valid_job_ids if not cache.exists(jid)]

    logger.info(f"Cached: {len(cached_ids)}, Uncached: {len(uncached_ids)}")

    # Fetch uncached jobs
    if uncached_ids:
        semaphore = asyncio.Semaphore(5)
        async with create_client() as client:
            details = await fetch_job_details(client, uncached_ids, semaphore)

        # Store in cache
        cache.put_batch([asdict(d) for d in details])

    # Return all (cached + freshly scraped)
    result = {}
    for jid in valid_job_ids:
        if cache.exists(jid):
            result[jid] = cache.get(jid)

    logger.info(f"Successfully retrieved metadata for {len(result)} jobs")
    return result


@mcp.resource("linkedinmcpfps://job_search_query/{location}/{distance}/{query}")
def compose_job_search_url(location: str = "San Francisco", distance: int = 25, query: str = "AI Engineer or ML Engineer") -> str:
    """
    Composes the URL to search for jobs in LinkedIn with proper URI encoding.

    Args:
        location: The location to search for jobs in LinkedIn
        distance: The distance from the location to search for jobs in LinkedIn
        query: The search query string for jobs in LinkedIn

    Returns:
        str: Properly encoded URL string
    """
    encoded_location = quote_plus(location)
    encoded_distance = quote_plus(str(distance))
    encoded_query = quote_plus(query)
    logger.info(f"Encoded query: {encoded_query}")
    return f"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search-results/?location={encoded_location}&distance={encoded_distance}&keywords={encoded_query}"


@mcp.tool()
def tailor_cv(
    job_description: str = "",
    position: str = "Research Engineer or ML Engineer or AI Engineer",
    location: str = "San Francisco",
    job_id: str = "first"
) -> list[base.Message]:
    """
    Tailors Francisco Perez-Sorrosal's CV to the position of the job description passed as parameter
    or retrieved from LinkedIn (for the particular location specified and based on the job id).

    Args:
        job_description: The job description to adapt the CV to (if not provided, use the job id to retrieve the job description)
        position: The position to search for jobs for (required)
        location: The location where the job should be located (required)
        job_id: The job id to retrieve the metadata for or "first"/"latest" (required)

    Returns:
        list[base.Message]: Instructions for CV tailoring process
    """
    logger.info(f"Adapting CV for position: {position}, location: {location}, job_id: {job_id}, job_description: {job_description}")
    return tailor_cv_to_job(job_description, position, location, job_id)


# TODO Maybe move this to the cv MCP Server and re-adapt the prompt.
@mcp.prompt()
def tailor_cv_to_job(
    job_description: str = "",
    position: str = "Research Engineer or ML Engineer or AI Engineer",
    location: str = "San Francisco",
    job_id: str = "first",
    pages: int = 1
) -> list[base.Message]:
    """Prompt for getting the latest job generating a tailored version of Francisco Perez-Sorrosal's CV based on the specified parameters.

    Args:
        job_description: The job description to adapt the CV to (if not provided, use the job id to retrieve the job description)
        position: The position to search for jobs for
        location: The location to search for jobs for
        job_id: The job id to retrieve the metadata for
        pages: The number of pages to retrieve the job description from

    Returns:
        list[base.Message]: The job details and the generated adapted CV tailored to the job description

    Raises:
        PromptLoadError: If the prompt file cannot be loaded
    """
    prompt_template = load_prompt_from_yaml("tailor_cv")
    formatted_prompt = prompt_template.format(
        job_description=job_description,
        position=position,
        location=location,
        job_id=job_id,
        pages=pages
    )
    return [base.UserMessage(formatted_prompt)]


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
