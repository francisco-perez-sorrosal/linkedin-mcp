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

- **query**: Job title or keywords (default: "AI Engineer or ML Engineer")
- **location**: City or region (default: "San Francisco")
- **distance**: Search radius in miles (default: 25; valid: 10, 25, 35, 50, 75, 100)
- **pages**: Number of result pages to scan (default: 1; max: 5)

If the user provides search terms in `$ARGUMENTS`, parse them naturally (e.g., "ML Engineer in New York" → query="ML Engineer", location="New York"). Otherwise, use the defaults above.

### Step 2: Search for Jobs

Call `search_jobs` with the gathered parameters:

```python
summaries = search_jobs(
    query=query,
    location=location,
    distance=distance,
    num_pages=num_pages
)
```

Results include job summaries: title, company, location, date, URL, job_id.

See [references/tool-mapping.md](references/tool-mapping.md) for full tool documentation and optional filter parameters.

### Step 3: Present Results

Display job summaries in a scannable table:

```
| # | Job Title | Company | Location | Posted |
|---|-----------|---------|----------|--------|
| 1 | ML Engineer | Acme Corp | SF, CA | 2 days ago |
```

Ask the user which jobs they want full details on. Accept selection by number, range ("1-3"), or "all".

### Step 4: Fetch Details

For selected jobs, call `get_job_details` with the selected job IDs.

Present each job's full metadata:
- Title, company, location
- Job description (key sections summarized, not raw HTML dump)
- Seniority level, employment type, job function
- Salary range (if available)
- Number of applicants
- Skills and industries

### Step 5: Next Actions

After presenting details, offer:
- "Tailor CV to this job" -- if the `cv-tailoring` skill is available
- "Search with different parameters"
- "Get details for more jobs from the list"

## Notes

- The LinkedIn MCP tools may take 10-30 seconds for detail retrieval (web scraping). Set expectations with the user.
- Job IDs are cached server-side. Repeated searches are faster.
- Maximum recommended batch: 20 jobs for detail retrieval.
