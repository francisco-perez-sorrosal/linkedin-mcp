# LinkedIn Job Search for Claude

A combined MCP server and skills system for searching LinkedIn jobs, retrieving detailed job metadata, and tailoring CVs. Integrates with Claude Desktop and Claude Code through both server-side tools and client-side workflow orchestration.

## Features

### MCP Server (Backend)
- **Async HTTP scraping** with httpx (no browser required)
- **Two-tier tool surface**: `search_jobs` + `get_job_details` for efficient data retrieval
- **JSONL-based caching** to avoid re-scraping jobs
- **LinkedIn guest API** integration for unauthenticated access
- **Semaphore-based concurrency control** with rate limiting and backoff

### Claude Code Skills (Frontend)
- **`linkedin-job-search`** — 5-step interactive workflow for searching and selecting jobs
- **`cv-tailoring`** — 3-phase methodology for adapting CVs to job descriptions
- **Default parameters** — San Francisco, "AI Engineer or ML Engineer" for quick searches

## Prerequisites

- Python 3.13+
- [Pixi](https://pixi.sh/) for dependency management
- [uv](https://github.com/astral-sh/uv) for building MCP bundles (optional)

## Installation

Clone the repository and install dependencies with Pixi:

```bash
git clone https://github.com/francisco-perez-sorrosal/linkedin-mcp.git
cd linkedin-mcp
pixi install
```

## Project Structure

```
linkedin-mcp/
├── src/linkedin_mcp_server/
│   ├── main.py          # FastMCP server with async tools
│   ├── scraper.py       # Async HTTP scraper (httpx + BeautifulSoup)
│   ├── cache.py         # JSONL persistent cache
│   ├── utils.py         # YAML prompt loader
│   └── prompts/
│       └── tailor_cv.yaml
├── skills/
│   ├── linkedin-job-search/  # Job search orchestration skill
│   └── cv-tailoring/         # CV tailoring skill
├── tests/
│   ├── test_cache.py
│   ├── test_scraper.py
│   └── fixtures/
└── pyproject.toml
```

## Running the Server

### Local Development

```bash
# stdio transport (for local Claude Desktop integration)
pixi run mcps --transport stdio

# streamable-http transport (for remote access)
pixi run mcps --transport streamable-http

# Direct execution with uv
uv run --with "mcp[cli]" mcp run src/linkedin_mcp_server/main.py --transport streamable-http
```

The HTTP server runs at `http://localhost:10000/mcp` by default.

### MCP Inspection Mode

```bash
DANGEROUSLY_OMIT_AUTH=true npx @modelcontextprotocol/inspector pixi run mcps --transport stdio
```

## Development Tasks

```bash
pixi run test      # Run tests
pixi run lint      # Check linting
pixi run format    # Apply formatting and fix lint issues
pixi run build     # Build package (creates sdist/wheel in dist/)
```

## MCP Tools

The server exposes three tools:

### 1. search_jobs

Search LinkedIn jobs and return summary data from search result cards.

```python
search_jobs(
    query="AI Engineer or ML Engineer",
    location="San Francisco",
    distance=25,
    num_pages=1,
    experience_level=None,  # 1-6: Intern to Executive
    job_type=None,          # F/P/C/T/V/I/O: Full-time, Part-time, Contract, etc.
    work_arrangement=None,  # 1/2/3: On-site, Remote, Hybrid
    time_posted=None        # r86400/r604800/r2592000: 24h, 1week, 1month
)
```

**Returns:** List of job summaries with title, company, location, date, URL, job_id.

### 2. get_job_details

Fetch full metadata for specific job IDs. Uses cache when available.

```python
get_job_details(job_ids=["123456789", "987654321"])
```

**Returns:** Dict mapping job_id to full metadata (description, seniority, employment type, applicants, salary, etc.).

### 3. tailor_cv

CV tailoring prompt orchestration (requires CV MCP server).

```python
tailor_cv(
    job_description="",
    position="Research Engineer or ML Engineer or AI Engineer",
    location="San Francisco",
    job_id="first"
)
```

**Returns:** Instructions for the CV tailoring workflow.

## Claude Desktop Integration

### Local Configuration (stdio)

Add to `claude_desktop_config.json`:

```json
{
  "linkedin_mcp_fps": {
    "command": "uv",
    "args": [
      "run",
      "--with", "mcp[cli]",
      "--with", "pymupdf4llm",
      "mcp", "run",
      "src/linkedin_mcp_server/main.py",
      "--transport", "streamable-http"
    ]
  }
}
```

### Remote Configuration (HTTP)

For connecting to a remote MCP server:

```json
{
  "linkedin_mcp_fps": {
    "command": "npx",
    "args": ["mcp-remote", "http://localhost:10000/mcp"]
  }
}
```

Replace the host and port as needed for your deployment.

### MCP Bundle (mcpb)

Build and install as an extension:

```bash
pixi run mcp-bundle
pixi run pack
```

The output file `linkedin-mcp-fps.mcpb` is created in `mcpb-package/`. Double-click to install in Claude Desktop.

## Claude Code Skills

Two client-side skills for workflow orchestration (located in `skills/`):

### linkedin-job-search

5-step interactive workflow: gather params → search → present table → fetch details → offer next actions. Activate with: "find jobs", "search positions", "job hunt".

### cv-tailoring

3-phase methodology for adapting Francisco's CV to job descriptions. Orchestrates LinkedIn MCP and CV MCP tools. Activate with: "tailor CV", "adapt resume", "CV for job".

See each skill's `SKILL.md` for detailed documentation.

## Architecture

### 1. MCP Server (`main.py`)

- Built with FastMCP framework
- Configurable transport modes: stdio, streamable-http
- Async/await with httpx for non-blocking HTTP operations
- Auto-detects transport mode from environment variables (TRANSPORT, HOST, PORT)

### 2. Async Scraper (`scraper.py`)

- Uses httpx AsyncClient for lightweight HTTP scraping
- LinkedIn guest API returns server-rendered HTML (no browser required)
- Semaphore-based concurrency control (default: 5 concurrent requests)
- Rate limiting with random delays (1-3s) and exponential backoff on 429/503
- Frozen dataclasses for type safety: `JobSummary`, `JobDetail`

### 3. Caching System (`cache.py`)

- JSONL-based persistent cache to avoid re-scraping jobs
- In-memory cache for fast lookups
- Batch insertion with `put_batch()` for efficient bulk updates
- Atomic flush with temp-file-then-rename for data integrity
- Default cache location: `~/.linkedin-mcp/raw_job_description_cache/`

## LinkedIn API Endpoints

The system uses LinkedIn's guest API:

- Job search: `https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search-results/`
- Job details: `https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}`

**Parameters:**
- `location`: Search location (URL encoded)
- `distance`: Radius in miles (10, 25, 35, 50, 75, 100)
- `keywords`: Job search query (URL encoded)
- `start`: Pagination offset
- Optional filters: `f_E` (experience), `f_JT` (job type), `f_WT` (work arrangement), `f_TPR` (time posted)

## Dependencies

| Package | Version | Role |
|---------|---------|------|
| `httpx` | >=0.28.1,<0.29 | Async HTTP client |
| `mcp[cli]` | >=1.9.2,<2 | FastMCP framework |
| `beautifulsoup4` | >=4.13.4,<5 | HTML parsing |
| `jsonlines` | >=4.0.0,<5 | JSONL cache persistence |
| `loguru` | >=0.7.3,<0.8 | Structured logging |
| `pyyaml` | >=6.0,<7 | YAML prompt loading |

All dependencies are managed via Pixi (see `pyproject.toml`).

## Cache Management

The system uses a local cache to avoid re-scraping jobs:

- **Location:** `~/.linkedin-mcp/raw_job_description_cache/`
- **Format:** JSONL (one job per line)
- **Automatic:** Cached jobs are returned immediately; uncached jobs trigger scraping and cache insertion
- **Persistence:** In-memory cache + on-disk JSONL file

To clear the cache, delete the directory manually.

## Deployment

### Remote Deployment (render.com)

Set environment variables in the deployment dashboard:

```bash
TRANSPORT=streamable-http
PORT=10000
```

Generate `requirements.txt` for render.com:

```bash
uv pip compile pyproject.toml > requirements.txt
```

Add `runtime.txt` with:

```txt
python-3.13.0
```

## Usage Examples

### Basic Job Search

```text
Search for ML Engineer jobs in San Francisco (2 pages)
```

### Retrieve Job Details

```text
Get full details for job IDs 1234567890 and 0987654321
```

### Combined Workflow with CV Tailoring

```text
Search for research engineer positions in New York,
show me the top results, then tailor Francisco's CV
to the most relevant job
```

### Using Skills

```text
@linkedin-job-search Find AI Engineer jobs in Seattle

@cv-tailoring Adapt Francisco's CV to job ID 4122691570
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Import errors | Run `pixi install` to install dependencies |
| Connection errors | Check internet connection; LinkedIn may be blocking requests |
| Rate limiting (429/503) | Reduce concurrency or wait before retrying (backoff is automatic) |
| Permission errors | Ensure the cache directory `~/.linkedin-mcp/` is writable |
| Empty results | Verify search parameters; some location/query combinations return no results |

## Support

For issues and feature requests, visit: https://github.com/francisco-perez-sorrosal/linkedin-mcp

## License

MIT License. See `pyproject.toml` for details.
