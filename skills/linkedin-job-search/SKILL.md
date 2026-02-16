---
name: linkedin-job-search
description: >
  Orchestrates LinkedIn job search using the LinkedIn MCP server tools.
  Searches for jobs by location and keywords, retrieves job summaries,
  and fetches detailed metadata for selected jobs. Activate when the user
  wants to search for jobs, find job listings, browse LinkedIn job postings,
  or look for positions. Trigger terms: job search, find jobs, LinkedIn jobs,
  job listings, search positions, job hunt.
allowed-tools:
  - "mcp__claude_ai_FPS_Linkedin_CV__*"
---

# LinkedIn Job Search

Search for LinkedIn jobs and retrieve detailed metadata using the LinkedIn MCP server.

## Workflow

### Step 1: Gather Search Parameters

Extract from `$ARGUMENTS` or use defaults:

- **keywords**: Job title or keywords (default: "AI Engineer or ML Engineer or Principal Research Engineer")
- **location**: City or region (default: "San Francisco, CA")
- **distance**: Search radius in miles (default: 25; valid: 10, 25, 35, 50, 75, 100)
- **limit**: Number of jobs to retrieve (default: 1; max: 10 for exploration, 20 for query)

If the user provides search terms in `$ARGUMENTS`, parse them naturally (e.g., "ML Engineer in New York" → keywords="ML Engineer", location="New York"). Otherwise, use the defaults above.

### Step 2: Search for Jobs

Choose the appropriate tool:

**For quick exploration** (live scraping, 1-10 recent jobs):
```python
results = explore_latest_jobs(
    keywords=keywords,
    location=location,
    distance=distance,
    limit=limit  # default: 1, max: 10
)
```

**For database queries** (instant, cached jobs with filters):
```python
results = query_jobs(
    keywords=keywords,
    location=location,
    remote_only=remote_only,
    visa_sponsorship=visa_sponsorship,
    limit=limit  # default: 20
)
```

Both return full job metadata including description insights.

See [references/tool-mapping.md](references/tool-mapping.md) for full tool documentation and optional filter parameters.

### Step 3: Present Results

Display jobs in a scannable format:

```
| # | Job Title | Company | Location | Posted | Remote | Visa |
|---|-----------|---------|----------|--------|--------|------|
| 1 | ML Engineer | Acme Corp | SF, CA | 2 days ago | ✓ | ✓ |
```

For each job, show:
- **Core**: title, company, location, posted date
- **Decision-making**: salary range, remote eligibility, visa sponsorship, applicants
- **Description insights** (if available): summary, key requirements, responsibilities
- **Metadata** (if requested): job URL, seniority level, employment type

### Step 4: Refine Search

If the user wants different results:
- Adjust filters (remote_only, visa_sponsorship, company, posted_after_hours)
- Change location or distance
- Modify keywords or increase limit

### Step 5: Next Actions

After presenting results, offer:
- "Refine search with different filters"
- "Explore more recent jobs (live scraping)"
- "Query database with different parameters"

## Notes

- **explore_latest_jobs()**: Live scraping, 10-30 seconds, returns 1-10 most recent jobs
- **query_jobs()**: Instant database queries, cached jobs, composable filters
- Database is populated by autonomous background scraping profiles
- Both tools return full metadata - no separate detail fetch needed
- Response sections are composable (use `include_*` flags to control token usage)
