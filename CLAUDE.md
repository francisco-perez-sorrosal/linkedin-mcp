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
pixi run test      # Run tests (117 tests, pytest configured)
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

This is a **LinkedIn MCP Server** with **autonomous background scraping** that exposes LinkedIn job data via the Model Context Protocol (MCP). The system has four main architectural components:

### 1. MCP Server (`main.py`)
- Built with FastMCP framework
- Configurable transport modes: stdio, streamable-http
- Exposes 11 tools for job querying, profile management, application tracking, and analytics
- Cache-first serving: queries return instantly from SQLite database
- Auto-detects transport mode from environment variables (TRANSPORT, HOST, PORT)

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
- Semaphore(10) for job detail scraping, Semaphore(2) for company enrichment
- Adaptive rate limiting with exponential backoff on 429/503 errors
- Graceful startup/shutdown with asyncio task coordination

### 4. Web Scraper (`scraper.py`)
- Async httpx for LinkedIn Guest API (no Selenium required)
- Enhanced extraction: salary parsing, remote/visa detection, skills extraction
- Company name normalization for fuzzy matching
- Frozen dataclasses for type safety: `JobSummary`, `JobDetail`
- Rate limiting with random delays (1-3s) and exponential backoff

### Key MCP Tools

**Job Query Tools:**
- `explore_latest_jobs(keywords, location, distance, limit)`: Live scraping for 1-10 most recent jobs (10-30s)
- `query_jobs(company, location, keywords, remote_only, visa_sponsorship, limit, ...)`: Instant database queries with composable filters (<100ms)

**Profile Management Tools:**
- `add_scraping_profile(name, location, keywords, distance, refresh_interval)`: Add autonomous scraping profile
- `list_scraping_profiles(enabled_only)`: List all scraping profiles
- `update_scraping_profile(profile_id, ...)`: Update profile configuration
- `delete_scraping_profile(profile_id, hard_delete)`: Disable or delete profile

**Application Tracking Tools:**
- `mark_job_applied(job_id, notes)`: Track job application
- `update_application_status(job_id, status, notes)`: Update application status
- `list_applications(status)`: Query applications by status

**Analytics Tools:**
- `get_cache_analytics()`: Database statistics and scraping profile status
- `get_job_changes(since_hours)`: Track field changes over time

## Architecture Decisions

Key architectural choices that are foundational to the system:

### SQLite over Redis/PostgreSQL
- **Decision**: Use SQLite for cache persistence
- **Rationale**: Zero deployment complexity, FTS5 full-text search, ACID guarantees, proven at 10K-100K rows
- **Trade-off**: Limited to single machine; no distributed caching (acceptable for personal job search)

### Async Tasks over Separate Process
- **Decision**: Run background scraper in MCP server process (asyncio tasks)
- **Rationale**: Single deployment unit, FastMCP lifespan hooks, no IPC needed
- **Trade-off**: Server crash kills scraper (mitigated by graceful error handling)

### Concurrency Limits
- **Job scraping**: Semaphore(10) - empirically validated as safe for LinkedIn
- **Company enrichment**: Semaphore(2) - conservative limit to avoid rate limiting
- **Rationale**: Balance between throughput and avoiding 429 errors

### Default Time Filter
- **Decision**: r7200 (2h) for default scraping profile
- **Rationale**: Fresher than 24h filter, empirically validated to return results
- **Configuration**: Adjustable per profile via `refresh_interval` parameter

### Metadata Extraction
- **Decision**: Regex-based patterns for skills/remote/visa detection
- **Rationale**: Simple, no ML dependencies, adequate precision for job search
- **Trade-off**: Less accurate than ML models (acceptable for filtering workflow)

## Known Limitations

### Rate Limiting
LinkedIn may return 429 errors if scraping too aggressively. The system uses exponential backoff and conservative default refresh intervals (2h). If rate limiting persists, increase `refresh_interval` or reduce active profiles.

### Database Write Contention
WAL mode enables concurrent reads, but writes are serialized. Batch writes every 10s reduce lock frequency. If contention occurs, reduce number of active scraping profiles.

### Company Enrichment Failures
Company pages may return 404 or have changed HTML structure. The system handles this gracefully (returns None, logs error). Companies remain in "needing refresh" state for retry on next cycle.

### Empty Cache on First Run
`query_jobs()` returns empty results until background scraper completes first run. Use `explore_latest_jobs()` for immediate results or wait for scraper to populate cache.

## Claude Code Skills

Client-side skill for workflow orchestration (located in `skills/`):

### `linkedin-job-search`
Interactive workflow for job searching (covers 2 of 11 MCP tools):
- Step 1: Gather search parameters (keywords, location, distance, limit)
- Step 2: Choose between live exploration (`explore_latest_jobs`) or database query (`query_jobs`)
- Step 3: Present results in scannable table format
- Step 4: Refine search with different filters
- Step 5: Offer next actions (refine, explore more, query database)

Uses `references/tool-mapping.md` for tool documentation and default parameters.

**Note**: Other tools (Profile Management, Application Tracking, Analytics) are accessed directly via MCP. Additional skills could be created for these categories (see Future Enhancements).

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
    main.py                  # FastMCP server, 11 async tools
    db.py                    # SQLite database layer with FTS5 search
    background_scraper.py    # Autonomous background scraping service
    scraper.py               # Async HTTP scraper (httpx + BeautifulSoup)
    models.py                # Pydantic response models (composable)
    migrate_cache.py         # JSONL → SQLite migration script
  skills/
    linkedin-job-search/     # Job search orchestration skill
      SKILL.md              # Skill definition and workflow
      references/
        tool-mapping.md      # MCP tool documentation
  tests/
    test_db.py               # Database unit tests
    test_scraper.py          # Scraper parsing tests
    test_background_scraper.py  # Background scraper tests
    test_integration.py      # End-to-end integration tests
    test_migrate_cache.py    # Migration script tests
    test_models.py           # Pydantic model tests
    fixtures/                # HTML fixtures for tests
```

## Dependencies

| Dependency | Version | Role |
|-----------|---------|------|
| `httpx` | >=0.28.1,<0.29 | Async HTTP client for LinkedIn API |
| `mcp[cli]` | >=1.9.2,<2 | FastMCP framework |
| `beautifulsoup4` | >=4.13.4,<5 | HTML parsing |
| `pydantic` | >=2.10.6,<3 | Composable response models with exclude_none |
| `loguru` | >=0.7.3,<0.8 | Structured logging |

**Removed:** `selenium`, `requests`, `jsonlines`, `pyyaml` (cache.py deleted, prompts moved to CV project)

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

## Future Enhancements

Deferred features that could enhance the system:

### Duplicate Detection (Fuzzy Matching)
Detect when the same job is reposted with a different job_id using fuzzy matching on (company, title, location) triplet. Prevents applying to the same job twice under different IDs.

### ML-Based Relevance Scoring
Score jobs by relevance to user's CV using sentence-transformers. Embed job descriptions and compute cosine similarity to CV for prioritization.

### Advanced Query Filters
Add salary range, applicant count, and company size filters to `query_jobs()` for more refined searches.

### Proxy Support
Rotate residential proxies to avoid rate limits, enabling more aggressive scraping schedules for high-volume use cases.

### Job Trend Analysis
Track posting trends over time (volume, salary trends, skills demand) for market research insights.

### Automated Backups
Daily backup script for SQLite database to enable recovery on corruption.

### Health Check Endpoint
HTTP endpoint for monitoring scraper health and error rates, enabling external monitoring integration.

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
