"""Integration tests for end-to-end workflows"""

import asyncio
import time
from pathlib import Path

import pytest

from linkedin_mcp_server.db import JobDatabase
from linkedin_mcp_server.background_scraper import BackgroundScraperService


@pytest.mark.asyncio
async def test_database_and_scraper_lifecycle(tmp_path):
    """Test database + background scraper initialization and shutdown"""
    db_path = tmp_path / "test.db"
    db = JobDatabase(db_path)
    db.initialize_schema()
    db.seed_default_profile()

    # Verify default profile created
    profiles = db.list_profiles(enabled_only=False)
    assert len(profiles) >= 1

    # Start background scraper
    scraper = BackgroundScraperService(db)
    await scraper.start()

    # Verify workers started
    assert len(scraper.worker_tasks) >= 1

    # Stop scraper gracefully
    await scraper.stop()

    # Verify all workers cancelled (tasks remain in dict but are cancelled)
    assert all(task.cancelled() or task.done() for task in scraper.worker_tasks.values())

    db.close()


@pytest.mark.asyncio
async def test_cache_query_performance(tmp_path):
    """Test that database queries are fast (<100ms)"""
    db_path = tmp_path / "test.db"
    db = JobDatabase(db_path)
    db.initialize_schema()

    # Insert 1000 test jobs
    jobs = [
        {
            "job_id": str(i),
            "title": f"Engineer {i}",
            "company": "Test Company",
            "normalized_company_name": "test company",
            "location": "San Francisco, CA",
            "posted_date": "2 days ago",
            "posted_date_iso": "2026-02-13T10:00:00Z",
            "scraped_at": "2026-02-15T10:00:00Z",
            "url": f"https://linkedin.com/jobs/{i}",
            "source": "linkedin",
            "raw_description": f"Description for job {i}",
            "employment_type": "Full-time",
            "seniority_level": "Mid-Senior level",
            "job_function": "Engineering",
            "industries": "Technology",
            "number_of_applicants": "10-50",
            "benefits_badge": "N/A",
            "remote_eligible": i % 2 == 0,  # Half remote
            "visa_sponsorship": i % 3 == 0,  # One third visa
        }
        for i in range(1000)
    ]
    db.upsert_jobs(jobs)

    # Measure query time
    start = time.time()
    result = db.query_jobs(limit=50)
    elapsed = time.time() - start

    # Verify performance (<100ms)
    assert elapsed < 0.1
    assert len(result) == 50

    # Test with filters
    start = time.time()
    remote_jobs = db.query_jobs(remote_only=True, limit=25)
    elapsed = time.time() - start

    assert elapsed < 0.1
    assert len(remote_jobs) <= 25
    assert all(job["remote_eligible"] == 1 for job in remote_jobs)

    db.close()


@pytest.mark.asyncio
async def test_profile_management_workflow(tmp_path):
    """Test profile add → update → disable → delete"""
    db_path = tmp_path / "test.db"
    db = JobDatabase(db_path)
    db.initialize_schema()

    # Add profile
    profile = {
        "name": "Test Profile",
        "location": "San Francisco, CA",
        "keywords": "ML Engineer",
        "distance": 25,
        "refresh_interval": 3600,
        "enabled": True,
    }
    profile_id = db.upsert_profile(profile)
    assert profile_id > 0

    # Verify profile created
    retrieved = db.get_profile(profile_id)
    assert retrieved is not None
    assert retrieved["name"] == "Test Profile"
    assert retrieved["enabled"] == 1

    # Update profile
    profile["keywords"] = "AI Engineer"
    profile["enabled"] = True
    db.upsert_profile(profile)

    updated = db.get_profile(profile_id)
    assert updated["keywords"] == "AI Engineer"

    # Disable profile (soft delete)
    db.delete_profile(profile_id, hard_delete=False)

    disabled = db.get_profile(profile_id)
    assert disabled["enabled"] == 0

    # Hard delete
    db.delete_profile(profile_id, hard_delete=True)

    deleted = db.get_profile(profile_id)
    assert deleted is None

    db.close()


@pytest.mark.asyncio
async def test_application_tracking_workflow(tmp_path):
    """Test mark applied → update status → query by status"""
    db_path = tmp_path / "test.db"
    db = JobDatabase(db_path)
    db.initialize_schema()

    # Create test jobs
    jobs = [
        {
            "job_id": f"job{i}",
            "title": f"Engineer {i}",
            "company": "Acme",
            "normalized_company_name": "acme",
            "location": "SF",
            "posted_date": "1 day ago",
            "posted_date_iso": "2026-02-14T10:00:00Z",
            "scraped_at": "2026-02-15T10:00:00Z",
            "url": f"https://linkedin.com/jobs/job{i}",
            "source": "linkedin",
            "raw_description": "Description",
            "employment_type": "Full-time",
            "seniority_level": "Mid",
            "job_function": "Engineering",
            "industries": "Tech",
            "number_of_applicants": "10",
            "benefits_badge": "N/A",
        }
        for i in range(5)
    ]
    db.upsert_jobs(jobs)

    # Mark jobs as applied
    assert db.mark_job_applied("job0", "Applied via LinkedIn")
    assert db.mark_job_applied("job1", "Applied directly")
    assert db.mark_job_applied("job2")

    # Update statuses
    assert db.update_application_status("job0", "interviewing", "Phone screen scheduled")
    assert db.update_application_status("job1", "rejected", "Not a fit")

    # Query by status
    applied = db.list_applications(status="applied")
    assert len(applied) == 1
    assert applied[0]["job_id"] == "job2"

    interviewing = db.list_applications(status="interviewing")
    assert len(interviewing) == 1
    assert interviewing[0]["job_id"] == "job0"

    rejected = db.list_applications(status="rejected")
    assert len(rejected) == 1
    assert rejected[0]["job_id"] == "job1"

    # List all applications
    all_apps = db.list_applications()
    assert len(all_apps) == 3

    db.close()


@pytest.mark.asyncio
async def test_analytics_completeness(tmp_path):
    """Test get_cache_analytics returns complete structure"""
    db_path = tmp_path / "test.db"
    db = JobDatabase(db_path)
    db.initialize_schema()
    db.seed_default_profile()

    # Insert sample data
    jobs = [
        {
            "job_id": f"job{i}",
            "title": f"Job {i}",
            "company": "Company",
            "normalized_company_name": "company",
            "location": "SF",
            "posted_date": "1 day ago",
            "posted_date_iso": "2026-02-14T10:00:00Z",
            "scraped_at": "2026-02-15T10:00:00Z",
            "url": f"https://linkedin.com/jobs/{i}",
            "source": "linkedin",
            "raw_description": "Description",
            "employment_type": "Full-time",
            "seniority_level": "Mid",
            "job_function": "Engineering",
            "industries": "Tech",
            "number_of_applicants": "10",
            "benefits_badge": "N/A",
        }
        for i in range(10)
    ]
    db.upsert_jobs(jobs)

    # Mark some as applied
    db.mark_job_applied("job0")
    db.mark_job_applied("job1")

    # Get analytics
    analytics = db.get_cache_analytics()

    # Verify structure
    assert "jobs" in analytics
    assert "by_age" in analytics["jobs"]
    assert "total" in analytics["jobs"]

    assert "scraping_profiles" in analytics
    assert len(analytics["scraping_profiles"]) >= 1

    assert "applications" in analytics
    assert analytics["applications"]["total"] == 2

    db.close()


@pytest.mark.asyncio
async def test_job_changes_tracking(tmp_path):
    """Test get_job_changes detects field changes"""
    db_path = tmp_path / "test.db"
    db = JobDatabase(db_path)
    db.initialize_schema()

    # Insert initial job
    job = {
        "job_id": "test123",
        "title": "ML Engineer",
        "company": "Acme",
        "normalized_company_name": "acme",
        "location": "SF",
        "posted_date": "1 day ago",
        "posted_date_iso": "2026-02-14T10:00:00Z",
        "scraped_at": "2026-02-15T10:00:00Z",
        "url": "https://linkedin.com/jobs/test123",
        "source": "linkedin",
        "raw_description": "Original description",
        "employment_type": "Full-time",
        "seniority_level": "Mid",
        "job_function": "Engineering",
        "industries": "Tech",
        "number_of_applicants": "10-50",
        "benefits_badge": "N/A",
        "salary_min": 150000,
        "salary_max": 200000,
    }
    db.upsert_jobs([job])

    # Record a change
    db.record_job_change(
        job_id="test123",
        field_name="salary_max",
        old_value=200000,
        new_value=220000
    )

    # Get changes
    changes = db.get_job_changes(since_hours=24)

    assert len(changes) >= 1
    assert any(c["job_id"] == "test123" and c["field_name"] == "salary_max" for c in changes)

    db.close()
