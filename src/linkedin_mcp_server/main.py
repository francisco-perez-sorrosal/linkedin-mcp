"""Main module for the LinkedIn MCP server with DXT compatibility."""

import asyncio
import os
import sys
import traceback
from dataclasses import asdict
from datetime import datetime, timezone

from loguru import logger
from mcp.server.fastmcp import FastMCP
from pathlib import Path

from linkedin_mcp_server.db import JobDatabase
from linkedin_mcp_server.background_scraper import BackgroundScraperService
from linkedin_mcp_server.models import (
    JobApplicationTracking,
    JobBenefits,
    JobCompanyEnrichment,
    JobCompleteSkills,
    JobCore,
    JobDecisionMaking,
    JobDescriptionInsights,
    JobEmploymentDetails,
    JobFullDescription,
    JobMetadata,
    JobResponse,
)
from linkedin_mcp_server.scraper import (
    create_client,
    fetch_job_details,
    search_jobs_pages,
)

# Configure logger for DXT environment
logger.remove()
logger.add(
    sys.stderr,
    level="INFO",
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    colorize=True
)

# Configure transport and statelessness
trspt = "stdio"
stateless_http = False
match os.environ.get("TRANSPORT", trspt):
    case "sse":
        trspt = "sse"
        stateless_http = False
        logger.warning("SSE transport is deprecated. Using stdio (locally) or streamable-http (remote) instead.")
    case "streamable-http":
        trspt = "streamable-http"
        stateless_http = True
    case _:
        trspt = "stdio"
        stateless_http = False


def find_project_root():
    current = Path(__file__).resolve()
    while current != current.parent:
        if (current / 'pyproject.toml').exists():
            return current
        current = current.parent
    return current


PROJECT_ROOT = find_project_root()


# Initialize FastMCP server with error handling
try:
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", 10000))
    mcp = FastMCP("linkedin_mcp_fps", stateless_http=stateless_http, host=host, port=port)
    logger.info(f"FastMCP server initialized with transport: {trspt}, host: {host}, port: {port}")
except Exception as e:
    logger.error(f"Failed to initialize FastMCP server: {e}")
    raise

# Global state for database and background scraper
db: JobDatabase | None = None
scraper_service: BackgroundScraperService | None = None


async def initialize_services():
    """Initialize database and background scraper on server startup"""
    global db, scraper_service

    logger.info("Initializing database and background scraper...")

    # Initialize database
    db_path = Path.home() / ".linkedin-mcp" / "jobs.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    db = JobDatabase(str(db_path))
    db.initialize_schema()
    logger.info(f"Database initialized at {db_path}")

    # Initialize and start background scraper
    scraper_service = BackgroundScraperService(db)
    await scraper_service.start()
    logger.info("Background scraper started")


async def shutdown_services():
    """Shutdown background scraper and close database"""
    global db, scraper_service

    logger.info("Shutting down background scraper and database...")

    if scraper_service:
        await scraper_service.stop()

    if db:
        db.close()

    logger.info("Shutdown complete")


@mcp.tool()
async def explore_latest_jobs(
    location: str = "San Francisco, CA",
    keywords: str = "AI Engineer or ML Engineer or Principal Research Engineer",
    distance: int = 25,
    limit: int = 1,
) -> dict:
    """
    Testing/exploration tool: Scrape latest LinkedIn jobs directly and return full details.

    Bypasses the database entirely - primarily for testing the scraper, quick exploration,
    or discovering jobs in new markets before creating a scraping profile.

    Returns the same structure as query_jobs() for consistency.

    Args:
        location: Search location (default: "San Francisco, CA")
        keywords: Search keywords (default: "AI Engineer or ML Engineer or Principal Research Engineer")
        distance: Search radius in miles (10, 25, 35, 50, 75, 100)
        limit: Maximum number of jobs to return (default: 1, max: 10)

    Returns:
        Dict with same structure as query_jobs():
        {
            "jobs": [JobResponse, ...],
            "returned": int,
            "total": int,
            "limit": int
        }
    """
    # Validate parameters
    if distance not in [10, 25, 35, 50, 75, 100]:
        logger.warning(f"Invalid distance {distance}, using default 25")
        distance = 25

    if limit < 1:
        limit = 1
    elif limit > 10:
        logger.warning(f"Limit {limit} too high, capping at 10 for testing")
        limit = 10

    # Calculate pages needed (10 jobs per page)
    num_pages = min((limit + 9) // 10, 10)  # Ceiling division, max 10 pages

    logger.info(f"🔍 Live exploration: '{keywords}' in {location} ({distance} miles, target: {limit} jobs)")

    async with create_client() as client:
        # Step 1: Get job summaries (contains job IDs)
        summaries = await search_jobs_pages(client, keywords, location, distance, num_pages, filters=None)

        if not summaries:
            logger.info("No jobs found in search results")
            return {"jobs": [], "returned": 0, "total": 0, "limit": limit}

        # Extract job IDs and limit to requested count
        job_ids = [s.job_id for s in summaries[:limit]]
        logger.info(f"Found {len(summaries)} jobs, fetching details for {len(job_ids)}")

        # Step 2: Fetch full job details
        semaphore = asyncio.Semaphore(5)
        job_details = await fetch_job_details(client, job_ids, semaphore)

    logger.info(f"Successfully scraped {len(job_details)} jobs")

    # Step 3: Convert to JobResponse Pydantic models (same as query_jobs)
    job_responses = []
    for detail in job_details:
        detail_dict = asdict(detail)

        # Build JobResponse (same structure as query_jobs)
        core = JobCore(
            job_id=detail_dict["job_id"],
            title=detail_dict["title"],
            company=detail_dict["company"],
            location=detail_dict["location"],
            posted_date=detail_dict["posted_date"],
            posted_date_iso=detail_dict.get("posted_date_iso", detail_dict["scraped_at"]),
        )

        decision_making = JobDecisionMaking(
            salary_range=detail_dict.get("salary", "N/A") if detail_dict.get("salary") != "N/A" else None,
            remote_eligible=detail_dict.get("remote_eligible", False),
            visa_sponsorship=detail_dict.get("visa_sponsorship", False),
            applicants=detail_dict.get("number_of_applicants"),
            easy_apply=detail_dict.get("easy_apply", False),
        )

        # Always include description insights for live exploration
        insights = JobDescriptionInsights(
            description_summary=detail_dict.get("raw_description", "")[:500] if detail_dict.get("raw_description") != "N/A" else None,
            key_requirements=[],  # Could parse from description if needed
            key_responsibilities_preview=None,
        )

        # Full description
        full_desc = JobFullDescription(
            description=detail_dict.get("raw_description") if detail_dict.get("raw_description") != "N/A" else None
        )

        # Employment details
        emp_details = JobEmploymentDetails(
            workplace_type="Remote" if detail_dict.get("remote_eligible") else None,
            experience_level=detail_dict.get("seniority_level") if detail_dict.get("seniority_level") != "N/A" else None,
            industry=detail_dict.get("industries") if detail_dict.get("industries") != "N/A" else None,
        )

        # Metadata
        metadata = JobMetadata(
            job_url=detail_dict.get("url") if detail_dict.get("url") != "N/A" else None,
            scraped_at=detail_dict["scraped_at"],
            last_seen=detail_dict["scraped_at"],
            seniority_level=detail_dict.get("seniority_level") if detail_dict.get("seniority_level") != "N/A" else None,
            employment_type=detail_dict.get("employment_type") if detail_dict.get("employment_type") != "N/A" else None,
        )

        job_response = JobResponse(
            core=core,
            decision_making=decision_making,
            description_insights=insights,
            full_description=full_desc,
            employment_details=emp_details,
            metadata=metadata,
        )

        job_responses.append(job_response.model_dump(exclude_none=True))

    logger.info(f"✅ Live exploration complete: {len(job_responses)} jobs returned")

    return {
        "jobs": job_responses,
        "returned": len(job_responses),
        "total": len(summaries),
        "limit": limit,
    }


@mcp.tool()
async def query_jobs(
    # Filters (all optional, composable)
    company: str | None = None,
    location: str | None = None,
    keywords: str | None = None,
    posted_after_hours: int | None = None,
    remote_only: bool = False,
    visa_sponsorship: bool = False,
    application_status: str | None = None,
    # Result control
    limit: int = 20,
    sort_by: str = "posted_date_iso",
    # Response sections (composable)
    include_description_insights: bool = True,
    include_application_tracking: bool = False,
    include_company_enrichment: bool = False,
    include_metadata: bool = False,
    include_full_description: bool = False,
    include_complete_skills: bool = False,
    include_benefits: bool = False,
    include_employment_details: bool = False,
) -> dict:
    """
    Query jobs from database cache with composable filters and response sections.

    Returns enriched summaries from cached data (instant, no network I/O).
    Response sections are configurable via include_* flags to minimize token usage.

    Core + decision_making fields are always included.
    Optional sections: description_insights, application_tracking, company_enrichment,
    metadata, full_description, complete_skills, benefits, employment_details.

    Args:
        company: Filter by company name (case-insensitive partial match)
        location: Filter by location (case-insensitive partial match)
        keywords: Full-text search keywords (searches title, description, etc.)
        posted_after_hours: Only jobs posted within last N hours
        remote_only: Only remote-eligible jobs
        visa_sponsorship: Only jobs offering visa sponsorship
        application_status: Filter by application status ("not_applied", "applied", etc.)
        limit: Maximum number of results to return (default: 20)
        sort_by: Sort order ("posted_date_iso", "scraped_at", or "applicants")
        include_description_insights: Include description summary and requirements
        include_application_tracking: Include application status and notes
        include_company_enrichment: Include company metadata
        include_metadata: Include URLs, timestamps, employment info
        include_full_description: Include complete job description
        include_complete_skills: Include required/preferred skills
        include_benefits: Include benefits list
        include_employment_details: Include workplace type, experience level

    Returns:
        Dict with "jobs" (list of job objects), "returned" (count), "total" (total matches),
        and "limit" fields
    """
    if not db:
        return {"error": "Database not initialized"}

    try:
        # Query database (returns list[dict] from SQLite rows)
        raw_jobs = db.query_jobs(
            company=company,
            location=location,
            keywords=keywords,
            posted_after_hours=posted_after_hours,
            remote_only=remote_only,
            visa_sponsorship=visa_sponsorship,
            application_status=application_status,
            limit=limit,
            offset=0,  # Always start from beginning - simplified interface
            sort_by=sort_by,
        )

        # Get total count for pagination
        total_count = db.count_jobs(
            company=company,
            location=location,
            keywords=keywords,
            posted_after_hours=posted_after_hours,
            remote_only=remote_only,
            visa_sponsorship=visa_sponsorship,
            application_status=application_status,
        )

        # Build composable responses
        job_responses = []
        for job in raw_jobs:
            # Core (always included)
            core = JobCore(
                job_id=job["job_id"],
                title=job["title"],
                company=job["company"],
                location=job["location"],
                posted_date=job["posted_date"],
                posted_date_iso=job["posted_date_iso"],
            )

            # Decision-making (always included)
            decision_making = JobDecisionMaking(
                salary_range=job.get("salary"),
                remote_eligible=bool(job.get("remote_eligible", False)),
                visa_sponsorship=bool(job.get("visa_sponsorship", False)),
                applicants=job.get("number_of_applicants"),
                easy_apply=bool(job.get("easy_apply", False)),
            )

            # Optional sections
            description_insights = None
            if include_description_insights:
                # Parse JSON fields if needed
                key_reqs = job.get("key_requirements")
                if isinstance(key_reqs, str):
                    import json
                    try:
                        key_reqs = json.loads(key_reqs)
                    except:
                        key_reqs = []

                description_insights = JobDescriptionInsights(
                    description_summary=job.get("description_summary"),
                    key_requirements=key_reqs if key_reqs else [],
                    key_responsibilities_preview=job.get(
                        "key_responsibilities_preview"
                    ),
                )

            application_tracking = None
            if include_application_tracking and job.get("application_status"):
                application_tracking = JobApplicationTracking(
                    application_status=job.get("application_status"),
                    applied_at=job.get("applied_at"),
                    application_notes=job.get("notes"),
                )

            company_enrichment = None
            if include_company_enrichment:
                specialties = job.get("specialties")
                if isinstance(specialties, str):
                    import json
                    try:
                        specialties = json.loads(specialties) if specialties else []
                    except:
                        specialties = []

                company_enrichment = JobCompanyEnrichment(
                    company_size=job.get("size"),
                    company_industry=job.get("industry"),
                    company_description=job.get("description"),
                    company_website=job.get("website"),
                    company_headquarters=job.get("headquarters"),
                    company_founded=job.get("founded"),
                    company_specialties=specialties if specialties else [],
                )

            metadata = None
            if include_metadata:
                metadata = JobMetadata(
                    job_url=job.get("url"),
                    scraped_at=job.get("scraped_at"),
                    last_seen=job.get("scraped_at"),
                    seniority_level=job.get("seniority_level"),
                    employment_type=job.get("employment_type"),
                )

            full_description = None
            if include_full_description:
                full_description = JobFullDescription(
                    description=job.get("raw_description"),
                )

            complete_skills = None
            if include_complete_skills:
                skills = job.get("skills")
                if isinstance(skills, str):
                    import json
                    try:
                        skills = json.loads(skills) if skills else []
                    except:
                        skills = []

                complete_skills = JobCompleteSkills(
                    skills_required=skills if skills else [],
                    skills_preferred=[],
                )

            benefits = None
            if include_benefits:
                benefits_list = []
                if job.get("benefits_badge"):
                    benefits_list = [job["benefits_badge"]]

                benefits = JobBenefits(benefits=benefits_list)

            employment_details = None
            if include_employment_details:
                employment_details = JobEmploymentDetails(
                    workplace_type="Remote"
                    if job.get("remote_eligible")
                    else "On-site",
                    experience_level=job.get("seniority_level"),
                    industry=job.get("industries"),
                )

            # Assemble response
            job_response = JobResponse(
                core=core,
                decision_making=decision_making,
                description_insights=description_insights,
                application_tracking=application_tracking,
                company_enrichment=company_enrichment,
                metadata=metadata,
                full_description=full_description,
                complete_skills=complete_skills,
                benefits=benefits,
                employment_details=employment_details,
            )

            job_responses.append(job_response.model_dump(exclude_none=True))

        response = {
            "jobs": job_responses,
            "returned": len(job_responses),
            "total": total_count,
            "limit": limit,
        }

        logger.info(
            f"query_jobs returned {len(job_responses)} of {total_count} jobs"
        )
        return response

    except Exception as e:
        logger.error(f"Error querying jobs: {e}")
        return {"error": str(e)}


# ===== Profile Management Tools =====

@mcp.tool()
async def add_scraping_profile(
    name: str,
    location: str,
    keywords: str,
    distance: int = 25,
    refresh_interval: int = 7200,
    time_filter: str = "r86400"
) -> dict:
    """
    Add a new scraping profile. Background scraper picks it up within 30s.

    Args:
        name: Unique name for the profile (e.g., "SF AI Jobs")
        location: Search location (e.g., "San Francisco, CA")
        keywords: Search keywords (e.g., "AI Engineer OR ML Engineer")
        distance: Search radius in miles (10, 25, 35, 50, 75, 100)
        refresh_interval: Scrape interval in seconds (min 3600 = 1 hour)
        time_filter: LinkedIn time filter (r86400=24h, r604800=7d, r2592000=30d)

    Returns:
        Created profile with ID and metadata
    """
    if not db:
        logger.error("Database not initialized")
        return {"error": "Database not initialized"}

    # Validate parameters
    if distance not in [10, 25, 35, 50, 75, 100]:
        return {"error": f"Invalid distance {distance}, must be one of [10, 25, 35, 50, 75, 100]"}

    if refresh_interval < 3600:  # Min 1 hour
        return {"error": "refresh_interval must be >= 3600 (1 hour)"}

    # Create profile dict
    profile = {
        "name": name,
        "location": location,
        "keywords": keywords,
        "distance": distance,
        "time_filter": time_filter,
        "refresh_interval": refresh_interval,
        "enabled": True,
    }

    try:
        profile_id = db.upsert_profile(profile)
        logger.info(f"Added scraping profile {profile_id}: {name}")

        # Return created profile with ID
        return {
            "id": profile_id,
            "name": name,
            "location": location,
            "keywords": keywords,
            "distance": distance,
            "time_filter": time_filter,
            "refresh_interval": refresh_interval,
            "enabled": True,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.error(f"Error adding profile: {e}")
        return {"error": str(e)}


@mcp.tool()
async def list_scraping_profiles(enabled_only: bool = False) -> list[dict]:
    """
    List all scraping profiles with status.

    Args:
        enabled_only: If True, only return enabled profiles

    Returns:
        List of profile dictionaries
    """
    if not db:
        logger.error("Database not initialized")
        return []

    try:
        profiles = db.list_profiles(enabled_only=enabled_only)
        logger.info(f"Retrieved {len(profiles)} profiles (enabled_only={enabled_only})")
        return profiles
    except Exception as e:
        logger.error(f"Error listing profiles: {e}")
        return []


@mcp.tool()
async def update_scraping_profile(
    profile_id: int,
    location: str | None = None,
    keywords: str | None = None,
    distance: int | None = None,
    refresh_interval: int | None = None,
    enabled: bool | None = None
) -> dict:
    """
    Update a scraping profile's configuration.

    Args:
        profile_id: ID of the profile to update
        location: New search location (optional)
        keywords: New search keywords (optional)
        distance: New search radius in miles (optional)
        refresh_interval: New scrape interval in seconds (optional)
        enabled: Enable/disable the profile (optional)

    Returns:
        Updated profile dictionary
    """
    if not db:
        logger.error("Database not initialized")
        return {"error": "Database not initialized"}

    # Validate distance if provided
    if distance is not None and distance not in [10, 25, 35, 50, 75, 100]:
        return {"error": f"Invalid distance {distance}, must be one of [10, 25, 35, 50, 75, 100]"}

    # Validate refresh_interval if provided
    if refresh_interval is not None and refresh_interval < 3600:
        return {"error": "refresh_interval must be >= 3600 (1 hour)"}

    try:
        # Get existing profile
        profile = db.get_profile(profile_id)
        if not profile:
            return {"error": f"Profile {profile_id} not found"}

        # Update fields
        if location is not None:
            profile["location"] = location
        if keywords is not None:
            profile["keywords"] = keywords
        if distance is not None:
            profile["distance"] = distance
        if refresh_interval is not None:
            profile["refresh_interval"] = refresh_interval
        if enabled is not None:
            profile["enabled"] = enabled

        # Upsert updated profile
        db.upsert_profile(profile)
        logger.info(f"Updated scraping profile {profile_id}")

        # Return updated profile
        updated_profile = db.get_profile(profile_id)
        if not updated_profile:
            return {"error": f"Failed to retrieve updated profile {profile_id}"}
        return updated_profile
    except Exception as e:
        logger.error(f"Error updating profile: {e}")
        return {"error": str(e)}


@mcp.tool()
async def delete_scraping_profile(profile_id: int, hard_delete: bool = False) -> dict:
    """
    Disable or delete a scraping profile. Jobs remain in database.

    Args:
        profile_id: ID of the profile to delete
        hard_delete: If True, permanently delete. If False (default), disable the profile.

    Returns:
        Status message
    """
    if not db:
        logger.error("Database not initialized")
        return {"error": "Database not initialized"}

    try:
        # Check if profile exists
        profile = db.get_profile(profile_id)
        if not profile:
            return {"error": f"Profile {profile_id} not found"}

        # Delete profile
        db.delete_profile(profile_id, hard_delete=hard_delete)

        action = "deleted" if hard_delete else "disabled"
        logger.info(f"{action.capitalize()} scraping profile {profile_id}")

        return {
            "status": action,
            "profile_id": profile_id,
            "message": f"Profile {profile_id} has been {action}"
        }
    except Exception as e:
        logger.error(f"Error deleting profile: {e}")
        return {"error": str(e)}


# ===== Application Tracking Tools =====

@mcp.tool()
async def mark_job_applied(job_id: str, notes: str = "") -> dict:
    """
    Mark that you've applied to a job.

    Args:
        job_id: LinkedIn job ID
        notes: Optional notes about the application

    Returns:
        Status dict with job_id and applied_at timestamp
    """
    if not db:
        logger.error("Database not initialized")
        return {"error": "Database not initialized"}

    try:
        success = db.mark_job_applied(job_id, notes)

        if success:
            logger.info(f"Marked job {job_id} as applied")
            return {
                "status": "success",
                "job_id": job_id,
                "applied_at": datetime.now(timezone.utc).isoformat(),
                "notes": notes
            }
        else:
            return {"error": f"Failed to mark job {job_id} as applied (job may not exist in database)"}
    except Exception as e:
        logger.error(f"Error marking job as applied: {e}")
        return {"error": str(e)}


@mcp.tool()
async def update_application_status(
    job_id: str,
    status: str,
    notes: str = ""
) -> dict:
    """
    Update application status for a job.

    Args:
        job_id: LinkedIn job ID
        status: New status (applied, interviewing, rejected, offered, accepted)
        notes: Optional notes about the status update

    Returns:
        Status dict with job_id and new_status
    """
    if not db:
        logger.error("Database not initialized")
        return {"error": "Database not initialized"}

    # Validate status
    valid_statuses = ["applied", "interviewing", "rejected", "offered", "accepted"]
    if status not in valid_statuses:
        return {"error": f"Invalid status '{status}', must be one of {valid_statuses}"}

    try:
        success = db.update_application_status(job_id, status, notes)

        if success:
            logger.info(f"Updated application status for job {job_id} to {status}")
            return {
                "status": "success",
                "job_id": job_id,
                "new_status": status,
                "notes": notes,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
        else:
            return {"error": f"Failed to update application status for job {job_id} (application may not exist)"}
    except Exception as e:
        logger.error(f"Error updating application status: {e}")
        return {"error": str(e)}


@mcp.tool()
async def list_applications(status: str | None = None) -> list[dict]:
    """
    List all job applications, optionally filtered by status.

    Args:
        status: Optional status filter (applied, interviewing, rejected, offered, accepted)

    Returns:
        List of application dictionaries with job details
    """
    if not db:
        logger.error("Database not initialized")
        return []

    # Validate status if provided
    if status:
        valid_statuses = ["applied", "interviewing", "rejected", "offered", "accepted"]
        if status not in valid_statuses:
            logger.error(f"Invalid status filter: {status}")
            return [{"error": f"Invalid status '{status}', must be one of {valid_statuses}"}]

    try:
        applications = db.list_applications(status)
        logger.info(f"Retrieved {len(applications)} applications" + (f" with status '{status}'" if status else ""))
        return applications
    except Exception as e:
        logger.error(f"Error listing applications: {e}")
        return []


# ===== Analytics and Job Changes Tools =====

@mcp.tool()
async def get_cache_analytics() -> dict:
    """
    Get detailed analytics about cached jobs, scraping profiles, applications, and overall health.

    Returns comprehensive statistics including:
    - Job counts by age (last 24h, 7d, 30d, older)
    - Scraping profile status and health
    - Application status breakdown
    - Company enrichment coverage
    - Cache size and health metrics
    """
    if not db:
        logger.error("Database not initialized")
        return {"error": "Database not initialized"}

    try:
        analytics = db.get_cache_analytics()
        logger.info("Retrieved cache analytics")
        return analytics
    except Exception as e:
        logger.error(f"Error retrieving cache analytics: {e}")
        return {"error": str(e)}


@mcp.tool()
async def get_job_changes(since_hours: int = 24) -> list[dict]:
    """
    Get jobs that have changed in the last N hours.

    Tracks changes to:
    - Salary range updates
    - Applicant count increases
    - Description modifications
    - Status changes

    Args:
        since_hours: Number of hours to look back (default 24)

    Returns:
        List of job change records with timestamps and field details
    """
    if not db:
        logger.error("Database not initialized")
        return []

    try:
        changes = db.get_job_changes(since_hours)
        logger.info(f"Retrieved {len(changes)} job changes in last {since_hours} hours")
        return changes
    except Exception as e:
        logger.error(f"Error retrieving job changes: {e}")
        return []


async def run_server():
    """Run the MCP server with background scraper lifecycle management"""
    try:
        # Initialize services
        await initialize_services()

        # Log server startup
        logger.info(f"Starting LinkedIn MCP server with {trspt} transport ({host}:{port}) and stateless_http={stateless_http}...")

        # Additional pre-flight checks
        if trspt == "stdio":
            logger.info("Using stdio transport - suitable for local Claude Desktop integration")
            await mcp.run_stdio_async()
        elif trspt == "streamable-http":
            logger.info(f"Using HTTP transport - server will be accessible at http://{host}:{port}/mcp")
            await mcp.run_streamable_http_async()
        else:
            logger.info(f"Using stdio transport (fallback)")
            await mcp.run_stdio_async()

    except KeyboardInterrupt:
        logger.info("Server shutdown requested by user")
    except Exception as e:
        logger.error(f"Fatal error running server: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise
    finally:
        # Ensure cleanup on exit
        await shutdown_services()


if __name__ == "__main__":
    try:
        # Log environment information for debugging
        logger.info(f"Python version: {sys.version}")
        logger.info(f"Current working directory: {os.getcwd()}")
        logger.info(f"Python path: {sys.path}")
        logger.info(f"Environment variables: TRANSPORT={os.environ.get('TRANSPORT')}, HOST={os.environ.get('HOST')}, PORT={os.environ.get('PORT')}")

        # Run server with async lifecycle management
        asyncio.run(run_server())

    except Exception as e:
        logger.error(f"Fatal error starting server: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        sys.exit(1)
