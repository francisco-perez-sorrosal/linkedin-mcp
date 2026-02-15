---
name: cv-tailoring
description: >
  Tailors Francisco Perez-Sorrosal's CV to a specific job description using
  a structured methodology. Orchestrates the LinkedIn MCP server (for job data)
  and the CV MCP server (for CV content). Activate when the user wants to
  adapt, tailor, customize, or optimize a CV/resume for a specific job posting
  or job description. Trigger terms: tailor CV, adapt resume, customize CV,
  CV for job, resume optimization, CV tailoring, match CV to job.
allowed-tools:
  - "mcp__claude_ai_FPS_Linkedin_CV__*"
  - "mcp__claude_ai_FPS_CV_Remote__*"
---

# CV Tailoring

Adapt Francisco's CV to a specific job description using a structured 3-phase methodology.

## Prerequisites

Before starting, ensure access to:
1. A job description (provided by user, or retrieved via LinkedIn MCP tools)
2. Francisco's CV content (retrieved via the CV MCP server tools)

## Workflow

### Step 1: Obtain Job Context

One of:
- **Job description provided directly**: Use the text as-is.
- **Job ID provided**: Call `get_job_details` (or `get_jobs_raw_metadata` for legacy) with the job ID to retrieve full metadata.
- **No job context**: Ask the user to either provide a job description, a job ID, or run a job search first (the `linkedin-job-search` skill handles this).

### Step 2: Retrieve CV Content

Call the CV MCP server tools (`mcp__claude_ai_FPS_CV_Remote__*`) to retrieve Francisco's current CV content. Use whatever tool the CV MCP server exposes for reading the full CV.

### Step 3: Apply Tailoring Methodology

Follow the full methodology in [references/methodology.md](references/methodology.md). The methodology has three phases:

1. **Strategic Analysis** -- Deconstruct the job, map Francisco's experience, assess fit (1-10), identify gaps
2. **Strategic CV Repositioning** -- Reorder sections, emphasize relevant skills, mirror job language, apply professional formatting
3. **Alignment Evaluation** -- Score across 7 competency areas, produce strategic positioning summary

### Step 4: Deliver Results

Produce four deliverables (see methodology for details):
1. Job Intelligence Brief (metadata table + fit score)
2. Strategically Repositioned CV (full markdown)
3. Strategic Alignment Assessment (scoring matrix)
4. Strategic Positioning Summary (400-600 words)

## Important Constraints

- **Content integrity**: Never add, modify, or fabricate information not in Francisco's original CV. Only reorganize and emphasize existing content.
- **Honest assessment**: Provide realistic scores. Acknowledge limitations while highlighting genuine strengths.
- **Professional formatting**: Use H2/H3 headers, consistent bullet structure, clean hierarchy.
