"""Main module for the LinkedIn MCP server with DXT compatibility."""

import os
import sys
import traceback
from typing import Any, Dict, List, Optional

from loguru import logger
from pathlib import Path

from urllib.parse import quote_plus, quote
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.prompts import base

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
def tailor_cv(
    job_description: str = "",
    position: str = "Research Engineer or ML Engineer or AI Engineer",
    location: str = "San Francisco",
    job_id: str = "first") -> list[base.Message]:
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
    """
    return  [base.UserMessage(f"""
You are a senior CV optimization specialist with 10+ years of experience in technical recruiting for computer science, machine learning, and artificial intelligence roles. Your expertise lies in strategic candidate positioning and maximizing job-candidate alignment through intelligent CV presentation.

OBJECTIVE:
Analyze a target job posting and strategically reposition Francisco's CV to showcase his most relevant qualifications while maintaining complete content integrity. Focus on strategic presentation rather than content modification.

<PREREQUISITES>
1. If the job description is not provided:
    1.1. Get a list of new jobs from linkedin ({pages} pages) for a {position} in {location}.
    1.2. Then, take the {job_id} job id from that list and retrieve its metadata context. 

2. If the job description is provided:
    2.1. Use this job description provided as metadata context: {job_description}

3. Finally, retrieve Francisco's CV content using the tools from the cv MCP Server. 
</PREREQUISITES>
    
With this context, follow the methodology below.

METHODOLOGY:

Follow the steps below and generate the deliverables specified taking into account the important notes.

<STEPS>

Phase 1: Strategic Analysis

Job Deconstruction: Extract key requirements, responsibilities, technical stack, and company culture indicators
Candidate Mapping: Identify Francisco's experiences that align with job priorities
Initial Fit Assessment: Evaluate the overall compatibility between Francisco's CV and the job requirements using a 1-10 scale (1 = poor fit, 10 = perfect match) based on technical skills overlap, experience level alignment, and role compatibility
Gap Assessment: Recognize any misalignments or areas requiring strategic positioning

Phase 2: Strategic CV Repositioning
Apply these proven techniques to optimize presentation:
Content Organization

- Reorder CV sections to lead with most relevant qualifications
- Restructure bullet points to emphasize job-relevant achievements first
- Position key technical skills prominently when they match requirements
- Elevate distributed systems and software engineering experience when relevant to role requirements

Strategic Emphasis

- Highlight terminology and keywords that mirror job posting language
- Emphasize quantifiable achievements that relate to role expectations
- Spotlight technologies and methodologies mentioned in job requirements
- Showcase Francisco's distributed systems expertise (scalability, performance, architecture) when applicable
- Feature software engineering best practices and development experience for technical roles
- Connect AI/ML work with underlying software engineering and systems foundations

Professional Formatting

- Use H2 headers for major sections (Summary, Experience, Skills, Education)
- Apply H3 headers for job titles and educational institutions
- Maintain consistent bullet point structure with action verbs
- Ensure clean hierarchy and scannable layout
- Create clear connections between Francisco's diverse technical backgrounds (AI/ML, distributed systems, software engineering)

Phase 3: Alignment Evaluation
Assess strategic positioning effectiveness across core competency areas.

</STEPS>

<DELIVERABLES>

Generate the following four sections in markdown format:

1. Job Intelligence Brief

1.1 Header: Job ID with clickable URL link and complete job title

1.2 Initial Fit Assessment: Provide an overall compatibility score (1-10 scale) with brief justification:

1.2.1 Overall Fit Score: X/10 - One sentence explaining the primary reasons for this initial assessment

1.3 Metadata Table: Include all available data points:

- Company name and industry
- Location and remote options
- Employment type (full-time, contract, etc.)
- Experience level required
- Salary range (if disclosed)
- Key technical requirements
- Application deadline (if specified)
- Direct application URL


2. Strategically Repositioned CV

Present Francisco's CV optimized for this specific role using professional markdown formatting. Prioritize sections and content based on job relevance while preserving all original information.

Formatting Requirements:

- Contact information prominently displayed
- Professional summary tailored to role (if applicable)
- Experience section ordered by relevance to target position
- Skills section highlighting job-relevant technologies
- Consistent formatting with clear visual hierarchy


3. Strategic Alignment Assessment

Evaluate positioning effectiveness using this scoring matrix (0-10 scale where 10 = perfect alignment):

Create a table with columns: Competency Area, Score, Strategic Rationale
Include these competency areas:

- Core Technical Skills: Assessment of alignment between Francisco's technical expertise and job requirements
- Experience Depth: Assessment of how Francisco's experience level matches role seniority
- Domain Knowledge: Relevance of Francisco's industry background to target company/sector
- Role-Specific Capabilities: Match between Francisco's demonstrated abilities and specific job responsibilities
- Technology Stack Alignment: Overlap between Francisco's technical tools and job requirements
- Growth Trajectory: Francisco's potential to advance within this role and company
- Cultural Integration: Likelihood of Francisco fitting company culture based on available indicators


4. Strategic Positioning Summary

Provide a concise strategic analysis (400-600 words) structured as follows:

- Competitive Advantages (150-200 words): Francisco's strongest qualifications that directly address this role's requirements
- Strategic Challenges (100-150 words): Any gaps or areas requiring careful positioning, with recommended mitigation strategies
- Value Proposition (150-250 words): The unique combination of skills and experience Francisco brings to this specific opportunity

</DELIVERABLES>

IMPORTANT NOTES:
- Content Integrity: Never add, modify, or fabricate any information not present in Francisco's original CV. Only reorganize and strategically emphasize existing content.
- Strategic Focus: Prioritize job description alignment above all other considerations. Every positioning decision should serve the goal of demonstrating Francisco's fit for this specific role.
- Professional Excellence: Maintain industry-standard CV formatting, consistent styling, and error-free presentation throughout.
- Honest Assessment: Provide realistic evaluation scores. Acknowledge limitations while highlighting genuine strengths.
    """)]


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
