# Tool Mapping

MCP tool names as registered in Claude Code for the LinkedIn MCP server.

## Server Configuration

**Server name:** `claude_ai_FPS_Linkedin_CV`

## Available Tools

| Logical Step | Tool Name | Key Parameters |
|-------------|-----------|----------------|
| Search jobs | `mcp__claude_ai_FPS_Linkedin_CV__search_jobs` | `query`, `location`, `distance`, `num_pages`, `experience_level`, `job_type`, `work_arrangement`, `time_posted` |
| Get job details | `mcp__claude_ai_FPS_Linkedin_CV__get_job_details` | `job_ids` (list of strings) |
| Tailor CV | `mcp__claude_ai_FPS_Linkedin_CV__tailor_cv` | `job_description`, `position`, `location`, `job_id` |

## Call Pattern

**Two-tier workflow:**

1. **Search for jobs** (fast, returns summaries)
   ```python
   summaries = search_jobs(
       location="San Francisco",
       query="ML Engineer",
       distance=25,
       num_pages=2
   )
   # Returns: list[dict] with keys:
   #   job_id, title, company, company_url, location,
   #   posted_date, posted_date_iso, job_url, benefits_badge
   ```

2. **Present summaries to user, get selection**

3. **Fetch details for selected jobs** (slower, cached when available)
   ```python
   details = get_job_details(job_ids=["123", "456", "789"])
   # Returns: dict[str, dict] mapping job_id to full metadata
   #   (title, company, location, description, salary,
   #    seniority, employment_type, skills, etc.)
   ```

## Default Parameters

When parameters are not specified, these defaults apply:

- `query`: "AI Engineer or ML Engineer"
- `location`: "San Francisco"
- `distance`: 25 (miles)
- `num_pages`: 1

## Optional Filters

The `search_jobs` tool accepts additional filter parameters:

| Parameter | Values | Description |
|-----------|--------|-------------|
| `experience_level` | "1"-"6" | 1=Intern, 2=Entry, 3=Associate, 4=Mid-Senior, 5=Director, 6=Executive |
| `job_type` | "F"/"P"/"C"/"T"/"V"/"I"/"O" | Full-time, Part-time, Contract, Temporary, Volunteer, Internship, Other |
| `work_arrangement` | "1"/"2"/"3" | On-site, Remote, Hybrid |
| `time_posted` | "r86400"/"r604800"/"r2592000" | Past 24 hours, Past week, Past month |

## Design Rationale

**Why two tiers?**
- **Search summaries** come from search result cards (10 jobs per page, fast)
- **Full details** require individual page fetches (1 request per job, slow)
- This allows scanning 20-30 job titles quickly, then fetching full details for only the 3-5 most promising ones
- Saves HTTP requests and time compared to fetching all details upfront
