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

# Development tasks
pixi run test      # Run tests (pytest required, not currently configured)
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
- Configurable transport modes: stdio, streamable-http (sse deprecated)
- Exposes async tools and resources for job searching and CV adaptation
- Auto-detects transport mode from environment variables (TRANSPORT, HOST, PORT)
- Uses async/await with httpx for non-blocking HTTP operations

### 2. Async Scraper (`scraper.py`)
- Uses httpx AsyncClient for lightweight HTTP scraping
- No browser/Selenium required — LinkedIn guest API returns server-rendered HTML
- Implements semaphore-based concurrency control (default: 5 concurrent requests)
- Rate limiting with random delays (1-3s) and exponential backoff on 429/503
- Frozen dataclasses for type safety: `JobSummary`, `JobDetail`
- Module-level functions for parsing and HTTP operations

### 3. Caching System (`cache.py`)
- JSONL-based persistent cache to avoid re-scraping jobs
- In-memory cache for fast lookups
- Batch insertion with `put_batch()` for efficient bulk updates
- Atomic flush with temp-file-then-rename for data integrity
- Default cache location: `~/.linkedin-mcp/raw_job_description_cache/`

### Key MCP Tools & Resources

**Two-Tier Tool Surface (v0.2.0):**
- `search_jobs(query, location, distance, num_pages, ...)`: Returns job summaries from search cards (fast)
- `get_job_details(job_ids)`: Fetches full metadata for specific jobs (cached when available)
- `tailor_cv(job_description, position, location, job_id)`: CV tailoring prompt orchestration
- Resource: `linkedinmcpfps://job_search_query/{location}/{distance}/{query}`

**Default Parameters:**
- Location: "San Francisco"
- Query: "AI Engineer or ML Engineer"
- Distance: 25 miles
- Pages: 1

## Claude Code Skills

Two client-side skills for workflow orchestration (located in `skills/`):

### `linkedin-job-search`
5-step interactive workflow: gather params → search → present table → fetch details → offer next actions. Uses tool-mapping.md for forward-compatibility with tool name changes.

### `cv-tailoring`
3-phase methodology for adapting Francisco's CV to job descriptions. Orchestrates both LinkedIn MCP and CV MCP tools. References detailed methodology in `skills/cv-tailoring/references/methodology.md`.

## LinkedIn URL Structure

The system uses LinkedIn's guest API endpoints:
- Job search: `https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search-results/`
- Job details: `https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}`

Parameters:
- `location`: Search location (URL encoded)
- `distance`: Radius in miles (10, 25, 35, 50, 75, 100)
- `keywords`: Job search query (URL encoded)
- `start`: Pagination offset
- Optional filters: `f_E` (experience), `f_JT` (job type), `f_WT` (work arrangement), `f_TPR` (time posted)

## Project Structure

```
linkedin-mcp/
  src/linkedin_mcp_server/
    main.py          # FastMCP server, async tools
    scraper.py       # Async HTTP scraper (httpx + BeautifulSoup)
    cache.py         # JSONL persistent cache
    utils.py         # YAML prompt loader
    prompts/
      tailor_cv.yaml # CV tailoring methodology
  skills/
    linkedin-job-search/  # Job search orchestration skill
    cv-tailoring/         # CV tailoring skill
  tests/
    test_cache.py    # Cache unit tests
    test_scraper.py  # Scraper parsing tests
    fixtures/        # HTML fixtures for tests
```

## Dependencies

| Dependency | Version | Role |
|-----------|---------|------|
| `httpx` | >=0.28.1,<0.29 | Async HTTP client (replaces requests + selenium) |
| `mcp[cli]` | >=1.9.2,<2 | FastMCP framework |
| `beautifulsoup4` | >=4.13.4,<5 | HTML parsing |
| `jsonlines` | >=4.0.0,<5 | JSONL cache persistence |
| `loguru` | >=0.7.3,<0.8 | Structured logging |
| `pyyaml` | >=6.0,<7 | YAML prompt loading |

**Removed (v0.2.0):** `selenium`, `requests` (replaced by async httpx pipeline)

## Deployment

- Supports both local (stdio) and remote (HTTP) MCP deployment
- Remote deployment configured for render.com with requirements.txt generation
- Environment variables: TRANSPORT, HOST, PORT

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
