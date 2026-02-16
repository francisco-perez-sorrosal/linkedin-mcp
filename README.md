# LinkedIn Job Search for Claude

An autonomous MCP server that continuously scrapes LinkedIn jobs and provides instant database-backed queries. Features background scraping profiles, application tracking, and composable response models.

## Features

### MCP Server (Backend)
- **Autonomous background scraping** — Configurable profiles that scrape continuously
- **SQLite database** with FTS5 full-text search and WAL mode for concurrent access
- **11 MCP tools** organized into 4 categories: Query, Profile Management, Application Tracking, Analytics
- **Cache-first serving** — Instant (<100ms) queries from local database
- **Async HTTP scraping** with httpx (no browser required)
- **Composable Pydantic models** — Token-efficient responses with `exclude_none=True`

### Integrated Features
1. **Job Querying** — Composable filters (company, location, keywords, remote, visa, posted date)
2. **Live Exploration** — On-demand scraping for 1-10 most recent jobs
3. **Profile Management** — Add/update/delete autonomous scraping profiles
4. **Application Tracking** — Track application status and notes
5. **Company Enrichment** — Automatic company metadata lookup
6. **Job Change Detection** — Audit log for field changes over time
7. **Analytics** — Database statistics and scraping profile health

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
│   ├── main.py                  # FastMCP server with 11 async tools
│   ├── db.py                    # SQLite database layer with FTS5 search
│   ├── background_scraper.py    # Autonomous background scraping service
│   ├── scraper.py               # Async HTTP scraper (httpx + BeautifulSoup)
│   ├── models.py                # Pydantic response models (composable)
│   └── migrate_cache.py         # JSONL → SQLite migration script
├── skills/
│   └── linkedin-job-search/     # Job search orchestration skill
│       ├── SKILL.md
│       └── references/
│           └── tool-mapping.md
├── tests/
│   ├── test_db.py               # Database unit tests (37 tests)
│   ├── test_scraper.py          # Scraper parsing tests (33 tests)
│   ├── test_background_scraper.py  # Background scraper tests (17 tests)
│   ├── test_integration.py      # End-to-end tests (6 tests)
│   ├── test_migrate_cache.py    # Migration tests (7 tests)
│   ├── test_models.py           # Pydantic model tests (17 tests)
│   └── fixtures/                # HTML fixtures for tests
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

The server exposes 11 tools organized into 4 categories. For detailed tool comparison, default parameters, and usage patterns, see `skills/linkedin-job-search/references/tool-mapping.md`.

### Job Query Tools

#### 1. explore_latest_jobs
Live scraping for 1-10 most recent jobs (10-30 seconds).

```python
explore_latest_jobs(
    keywords="AI Engineer or ML Engineer or Principal Research Engineer",
    location="San Francisco, CA",
    distance=25,  # miles
    limit=1       # max 10
)
```

#### 2. query_jobs
Instant database queries with composable filters (<100ms).

```python
query_jobs(
    company="Anthropic",
    location="San Francisco",
    keywords="ML Engineer",
    posted_after_hours=168,  # Last week
    remote_only=True,
    visa_sponsorship=True,
    limit=20,
    sort_by="posted_date_iso",
    include_description_insights=True,
    include_metadata=False,
    include_full_description=False
)
```

### Profile Management Tools

#### 3. add_scraping_profile
Add autonomous scraping profile (worker spawns within 30s).

#### 4. list_scraping_profiles
List all scraping profiles with status.

#### 5. update_scraping_profile
Update profile configuration (changes apply on next reload).

#### 6. delete_scraping_profile
Disable (soft delete) or permanently delete profile.

### Application Tracking Tools

#### 7. mark_job_applied
Track job application with optional notes.

#### 8. update_application_status
Update status (applied → interviewing → offered/rejected).

#### 9. list_applications
Query applications by status.

### Analytics Tools

#### 10. get_cache_analytics
Database statistics, scraping profile health, application counts.

#### 11. get_job_changes
Audit log of field changes over time.

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

Client-side skill for workflow orchestration (located in `skills/`):

### linkedin-job-search

Interactive workflow for job searching:
- Step 1: Gather search parameters (keywords, location, distance, limit)
- Step 2: Choose between live exploration or database query
- Step 3: Present results in scannable table
- Step 4: Refine search with different filters
- Step 5: Offer next actions

Activate with: "find jobs", "search positions", "job hunt".

See `skills/linkedin-job-search/SKILL.md` for detailed documentation.

## Architecture

### 1. MCP Server (`main.py`)

- Built with FastMCP framework
- Configurable transport modes: stdio, streamable-http
- 11 async tools for job querying, profile management, application tracking, and analytics
- Cache-first serving: queries return instantly from SQLite database
- Auto-detects transport mode from environment variables

### 2. Database Layer (`db.py`)

- SQLite with WAL mode for concurrent reads/writes
- FTS5 full-text search on job descriptions and titles
- 5 tables: jobs, scraping_profiles, applications, company_enrichment, job_changes
- Default location: `~/.linkedin-mcp/jobs.db`
- Composable queries with multiple filters
- Performance: <100ms for typical queries

### 3. Background Scraper Service (`background_scraper.py`)

- Runs continuously in MCP server process (async tasks)
- One worker per scraping profile (configurable via MCP tools)
- Default profile: San Francisco, CA, 25mi, "AI Engineer or ML Engineer or Principal Research Engineer", 2h refresh
- Semaphore(10) for job scraping, Semaphore(2) for company enrichment
- Adaptive rate limiting with exponential backoff
- Graceful startup/shutdown with asyncio task coordination

### 4. Web Scraper (`scraper.py`)

- Async httpx for LinkedIn Guest API (no Selenium required)
- Enhanced extraction: salary parsing, remote/visa detection, skills extraction
- Company name normalization for fuzzy matching
- Frozen dataclasses for type safety: `JobSummary`, `JobDetail`
- Rate limiting with random delays (1-3s) and exponential backoff

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
| `httpx` | >=0.28.1,<0.29 | Async HTTP client for LinkedIn API |
| `mcp[cli]` | >=1.9.2,<2 | FastMCP framework |
| `beautifulsoup4` | >=4.13.4,<5 | HTML parsing |
| `pydantic` | >=2.10.6,<3 | Composable response models with exclude_none |
| `loguru` | >=0.7.3,<0.8 | Structured logging |

**Removed:** `selenium`, `requests`, `jsonlines`, `pyyaml` (cache.py deleted, moved to SQLite)

All dependencies are managed via Pixi (see `pyproject.toml`).

## Migration from JSONL Cache

If you have existing JSONL cache from v0.2.0, run the migration script:

```bash
pixi run python src/linkedin_mcp_server/migrate_cache.py
```

This will:
- Backup existing JSONL cache (creates `.jsonl.backup`)
- Migrate all jobs to SQLite database at `~/.linkedin-mcp/jobs.db`
- Transform and populate enhanced fields (salary, remote, visa, skills)
- Preserve all original job data

The migration is idempotent and can be safely rerun. After migration, the JSONL cache is no longer used.

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

### Query Cached Jobs

```text
Find remote ML Engineer jobs at Anthropic posted in the last week
```

### Live Exploration

```text
Explore the 5 most recent AI Engineer jobs in Seattle
```

### Profile Management

```text
Add a scraping profile for Research Engineer jobs in Boston, 35 mile radius, refresh every 4 hours
```

### Application Tracking

```text
Mark job 1234567890 as applied with note "Applied via company website"
```

```text
Update application status for job 1234567890 to interviewing with note "Phone screen scheduled for Friday"
```

### Analytics

```text
Show me cache analytics and scraping profile status
```

### Using Skills

```text
@linkedin-job-search Find remote Python Engineer jobs in New York
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Import errors | Run `pixi install` to install dependencies |
| Database locked | Another process may have the database open; close other connections |
| Background scraper not running | Check logs; verify profile is enabled in `list_scraping_profiles()` |
| Empty query results | Database may be empty; wait for first scrape or use `explore_latest_jobs()` |
| Rate limiting (429/503) | Automatic backoff; check logs for error rates |
| Permission errors | Ensure `~/.linkedin-mcp/` directory is writable |
| Migration failed | Restore from `.jsonl.backup` and retry; check logs for errors |

## Future Enhancements

### Additional Client-Side Skills
Create workflow orchestration skills for uncovered tool categories:
- **Profile Management Skill** — Interactive workflow for configuring autonomous scraping profiles
- **Application Tracking Skill** — Guide user through marking applications and tracking status changes
- **Analytics Skill** — Present cache statistics and job trends in scannable format

Currently, only job search has a dedicated skill. Other tools are accessed directly via MCP.

See CLAUDE.md Future Enhancements section for additional features (duplicate detection, ML scoring, proxy support, etc.).

## Support

For issues and feature requests, visit: https://github.com/francisco-perez-sorrosal/linkedin-mcp

## License

MIT License. See `pyproject.toml` for details.
