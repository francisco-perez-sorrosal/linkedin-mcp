# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

This project uses **Pixi** for dependency management and task execution. Key commands:

```bash
# Install dependencies
pixi install

# Run MCP server
pixi run mcps --transport stdio           # For local development
pixi run mcps --transport streamable-http # For remote/HTTP access

# Run web scraper directly  
pixi run linkedin_scrapper

# Development tasks
pixi run test      # Run tests
pixi run lint      # Check linting
pixi run format    # Apply formatting and fix lint issues
pixi run build     # Build package (creates sdist/wheel in dist/)
```

Alternative execution methods:
```bash
# Direct execution with uv
uv run --with "mcp[cli]" mcp run src/linkedin_mcp_server/main.py --transport streamable-http

# MCP inspection mode
DANGEROUSLY_OMIT_AUTH=true npx @modelcontextprotocol/inspector pixi run mcps --transport stdio
```

## Architecture Overview

This is a **LinkedIn MCP Server** that exposes LinkedIn job data via the Model Context Protocol (MCP). The system has three main architectural components:

### 1. MCP Server (`main.py`)
- Built with FastMCP framework
- Configurable transport modes: stdio, sse (deprecated), streamable-http
- Exposes tools and resources for job searching and CV adaptation
- Auto-detects transport mode from environment variables (TRANSPORT, HOST, PORT)

### 2. Web Scraper (`web_scrapper.py`) 
- Uses Selenium WebDriver for LinkedIn job scraping
- Implements multiprocessing for parallel job extraction (limited to 2 processes)
- Scrapes comprehensive job metadata: title, company, location, description, requirements, etc.
- Handles LinkedIn's dynamic content and various page layouts

### 3. Caching System (`cache.py`)
- JSONL-based persistent cache to avoid re-scraping jobs
- In-memory cache for fast lookups
- Configurable cache keys and storage locations
- Default cache location: `~/.linkedin-mcp/raw_job_description_cache/`

### Key MCP Tools & Resources
- `get_url_for_jobs_search()`: Generates LinkedIn job search URLs
- `get_new_job_ids()`: Retrieves job IDs from LinkedIn pages
- `get_jobs_raw_metadata()`: Gets detailed job information
- `adapt_cv_to_latest_job()`: Adapts Francisco's CV to job descriptions
- Resource: `linkedinmcpfps://job_search_query/{location}/{distance}/{query}`

## LinkedIn URL Structure

The system uses LinkedIn's guest API endpoints:
- Job search: `https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search-results/`
- Job details: `https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}`

Parameters:
- `location`: Search location (URL encoded)
- `distance`: Radius in miles (10, 25, 35, 50, 75, 100)
- `keywords`: Job search query (URL encoded)
- `start`: Pagination offset

## Project Structure Notes

- Uses `src/` layout for Python packaging
- Source code in `src/linkedin_mcp_server/`
- Supports both local (stdio) and remote (HTTP) MCP deployment
- Remote deployment configured for render.com with requirements.txt generation
- Environment variables: TRANSPORT, HOST, PORT for deployment configuration

## Claude Desktop Integration

Local configuration:
```json
{
  "linkedin_mcp_fps": {
    "command": "uv",
    "args": ["run", "--with", "mcp[cli]", "--with", "pymupdf4llm", "mcp", "run", "src/linkedin_mcp_server/main.py", "--transport", "streamable-http"]
  }
}
```

Remote configuration:
```json
{
  "linkedin_mcp_fps": {
    "command": "npx",
    "args": ["mcp-remote", "http://localhost:10000/mcp"]
  }
}
```

Prefer delegating to specialized agents (researcher, context-engineer, implementer, etc.) over doing multi-step work directly.
