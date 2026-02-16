"""One-time migration script: JSONL cache → SQLite database"""

import json
import shutil
from pathlib import Path
from datetime import datetime, timezone

from loguru import logger

from linkedin_mcp_server.db import JobDatabase, normalize_company_name
from linkedin_mcp_server.scraper import (
    extract_salary_structured,
    extract_remote_eligibility,
    extract_visa_sponsorship,
    extract_skills,
)


def migrate_jsonl_to_sqlite(
    jsonl_path: Path,
    db_path: Path,
    backup: bool = True
) -> int:
    """
    Migrate JSONL cache to SQLite database.

    Args:
        jsonl_path: Path to existing JSONL cache file
        db_path: Path to SQLite database file
        backup: If True, create backup of JSONL file

    Returns:
        Number of jobs migrated
    """
    if not jsonl_path.exists():
        logger.warning(f"JSONL cache not found at {jsonl_path}")
        return 0

    # Create backup
    if backup:
        backup_path = jsonl_path.with_suffix('.jsonl.backup')
        shutil.copy(jsonl_path, backup_path)
        logger.info(f"Created backup at {backup_path}")

    # Initialize database
    db = JobDatabase(db_path)
    db.initialize_schema()

    # Read JSONL records
    jobs = []
    with open(jsonl_path, 'r') as f:
        for line_num, line in enumerate(f, 1):
            try:
                job = json.loads(line)

                # Transform to new schema
                transformed_job = transform_job_record(job)
                jobs.append(transformed_job)

            except json.JSONDecodeError as e:
                logger.error(f"Error parsing JSONL line {line_num}: {e}")
                continue
            except Exception as e:
                logger.error(f"Error transforming job on line {line_num}: {e}")
                continue

    # Batch insert
    if jobs:
        count = db.upsert_jobs(jobs)
        logger.info(f"Migrated {count} jobs from JSONL to SQLite")
    else:
        count = 0
        logger.info("No jobs to migrate")

    db.close()
    return count


def transform_job_record(old_job: dict) -> dict:
    """
    Transform old JSONL job record to new schema.

    Old schema (JobDetail from scraper.py):
        job_id, url, source, scraped_at, title, company, company_url,
        location, posted_date, number_of_applicants, salary, raw_description,
        employment_type, seniority_level, job_function, industries, skills,
        company_details

    New schema (jobs table):
        + salary_min, salary_max, salary_currency, equity_offered
        + remote_eligible, visa_sponsorship, skills (parsed)
        + easy_apply, normalized_company_name, posted_date_iso
        + profile_id (set to None for migrated jobs)
    """
    # Parse enhanced fields from raw data
    salary_str = old_job.get("salary", "N/A")
    salary_data = extract_salary_structured(salary_str)

    raw_desc = old_job.get("raw_description", "")
    remote = extract_remote_eligibility(raw_desc)
    visa = extract_visa_sponsorship(raw_desc)
    skills = extract_skills(raw_desc)

    # Get company name
    company = old_job.get("company", "N/A")

    # Handle posted_date_iso - use scraped_at as fallback
    scraped_at = old_job.get("scraped_at")
    if not scraped_at:
        scraped_at = datetime.now(timezone.utc).isoformat()

    # Transform
    new_job = {
        "job_id": old_job.get("job_id"),
        "title": old_job.get("title", "N/A"),
        "company": company,
        "normalized_company_name": normalize_company_name(company),
        "company_url": old_job.get("company_url", "N/A"),
        "location": old_job.get("location", "N/A"),
        "posted_date": old_job.get("posted_date", "N/A"),
        "posted_date_iso": scraped_at,  # Fallback to scraped_at
        "scraped_at": scraped_at,
        "salary_min": salary_data["min"],
        "salary_max": salary_data["max"],
        "salary_currency": salary_data["currency"],
        "equity_offered": salary_data["equity_offered"],
        "raw_description": raw_desc,
        "employment_type": old_job.get("employment_type", "N/A"),
        "seniority_level": old_job.get("seniority_level", "N/A"),
        "job_function": old_job.get("job_function", "N/A"),
        "industries": old_job.get("industries", "N/A"),
        "number_of_applicants": old_job.get("number_of_applicants", "N/A"),
        "benefits_badge": "N/A",  # Not in old schema
        "url": old_job.get("url", "N/A"),
        "source": old_job.get("source", "linkedin"),
        "remote_eligible": remote,
        "visa_sponsorship": visa,
        "skills": ", ".join(skills) if skills else "N/A",
        "easy_apply": False,  # Not in old schema
        "profile_id": None  # Migrated jobs have no profile
    }

    return new_job


if __name__ == "__main__":
    # Default paths
    jsonl_path = Path.home() / ".linkedin-mcp" / "raw_job_description_cache" / "raw_job_descriptions.jsonl"
    db_path = Path.home() / ".linkedin-mcp" / "jobs.db"

    logger.info("Starting JSONL → SQLite migration...")
    logger.info(f"JSONL path: {jsonl_path}")
    logger.info(f"Database path: {db_path}")

    count = migrate_jsonl_to_sqlite(jsonl_path, db_path, backup=True)
    logger.info(f"Migration complete: {count} jobs migrated")
