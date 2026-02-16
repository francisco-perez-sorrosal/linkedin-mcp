# Tool Mapping

MCP tool names as registered in Claude Code for the LinkedIn MCP server.

## Server Configuration

**Server name:** `claude_ai_FPS_Linkedin_CV`

## Available Tools

| Purpose | Tool Name | Key Parameters |
|---------|-----------|----------------|
| Live exploration | `mcp__claude_ai_FPS_Linkedin_CV__explore_latest_jobs` | `location`, `keywords`, `distance`, `limit` |
| Database queries | `mcp__claude_ai_FPS_Linkedin_CV__query_jobs` | `company`, `location`, `keywords`, `posted_after_hours`, `remote_only`, `visa_sponsorship`, `limit`, `sort_by`, `include_*` |

## Tool Comparison

### explore_latest_jobs()
- **Purpose**: Quick exploration of latest LinkedIn jobs
- **Data source**: Live web scraping
- **Speed**: 10-30 seconds
- **Limit**: 1-10 jobs (default: 1)
- **Use when**: User wants fresh, recent jobs; database may be stale

```python
results = explore_latest_jobs(
    location="San Francisco, CA",
    keywords="AI Engineer or ML Engineer or Principal Research Engineer",
    distance=25,
    limit=1  # Max 10
)
# Returns: {"jobs": [...], "returned": N, "total": N, "limit": L}
```

### query_jobs()
- **Purpose**: Fast database queries with composable filters
- **Data source**: SQLite cache (populated by background scraping)
- **Speed**: Instant (<100ms)
- **Limit**: Up to 20 jobs (default: 20)
- **Use when**: User wants filtered results, remote jobs, visa sponsorship, company search

```python
results = query_jobs(
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
    include_full_description=False,
)
# Returns: {"jobs": [...], "returned": N, "total": M, "limit": L}
```

## Default Parameters

When parameters are not specified, these defaults apply:

**explore_latest_jobs**:
- `keywords`: "AI Engineer or ML Engineer or Principal Research Engineer"
- `location`: "San Francisco, CA"
- `distance`: 25 (miles)
- `limit`: 1

**query_jobs**:
- `limit`: 20
- `sort_by`: "posted_date_iso"
- `include_description_insights`: True
- All other `include_*` flags: False

## Response Structure

Both tools return the same structure with composable Pydantic models:

```json
{
  "jobs": [
    {
      "core": {
        "job_id": "123456",
        "title": "ML Engineer",
        "company": "Anthropic",
        "location": "San Francisco, CA",
        "posted_date": "2 days ago",
        "posted_date_iso": "2026-02-13T10:00:00Z"
      },
      "decision_making": {
        "salary_range": "$150K - $200K",
        "remote_eligible": true,
        "visa_sponsorship": true,
        "applicants": "50-100 applicants",
        "easy_apply": false
      },
      "description_insights": {
        "description_summary": "We are hiring...",
        "key_requirements": ["Python", "PyTorch", "AWS"],
        "key_responsibilities_preview": "Design and implement..."
      },
      "metadata": {  // Only if include_metadata=True
        "job_url": "https://linkedin.com/jobs/view/123456",
        "scraped_at": "2026-02-15T10:00:00Z",
        "seniority_level": "Mid-Senior level",
        "employment_type": "Full-time"
      }
    }
  ],
  "returned": 1,
  "total": 1,
  "limit": 1
}
```

## Composable Response Sections (query_jobs only)

Control token usage with `include_*` flags:

| Flag | Section | Use When |
|------|---------|----------|
| `include_description_insights` (default: True) | `description_insights` | User needs summary and requirements |
| `include_application_tracking` | `application_tracking` | User wants to see application status |
| `include_company_enrichment` | `company_enrichment` | User needs company info |
| `include_metadata` | `metadata` | User needs URLs and timestamps |
| `include_full_description` | `full_description` | User wants complete job description |
| `include_complete_skills` | `complete_skills` | User wants full skills list |
| `include_benefits` | `benefits` | User wants benefits info |
| `include_employment_details` | `employment_details` | User wants workplace type, experience level |

**Core** and **decision_making** sections are always included.

## Design Rationale

**Why two tools?**
- **explore_latest_jobs**: Live scraping for fresh jobs when database is empty or stale
- **query_jobs**: Instant queries with powerful filters for cached jobs
- Database is populated by autonomous background scraping profiles
- Both return full metadata - no separate detail fetch needed

**Why no pagination?**
- Simplified interface - users specify `limit` only
- For more results, increase `limit` rather than managing offsets
- Aligns with agent-friendly API design
