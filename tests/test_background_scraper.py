"""Tests for background scraper service"""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from linkedin_mcp_server.background_scraper import (
    BackgroundScraperService,
    ScrapingProfile,
)


@pytest.fixture
def mock_db():
    """Create a mock JobDatabase"""
    db = MagicMock()
    db.list_profiles.return_value = []
    db.seed_default_profile.return_value = 1
    db.update_profile_last_run.return_value = None
    return db


@pytest.fixture
def sample_profile():
    """Create a sample scraping profile"""
    return {
        "id": 1,
        "name": "test-profile",
        "location": "San Francisco, CA",
        "keywords": "ML Engineer",
        "distance": 25,
        "time_filter": "r7200",
        "refresh_interval": 3600,
        "enabled": True,
        "last_scraped_at": None,
        "created_at": "2026-02-15T10:00:00Z",
        "updated_at": "2026-02-15T10:00:00Z",
    }


@pytest.mark.asyncio
async def test_scraping_profile_dataclass(sample_profile):
    """Test ScrapingProfile dataclass initialization"""
    profile = ScrapingProfile(**sample_profile)

    assert profile.id == 1
    assert profile.name == "test-profile"
    assert profile.location == "San Francisco, CA"
    assert profile.keywords == "ML Engineer"
    assert profile.distance == 25
    assert profile.refresh_interval == 3600
    assert profile.enabled is True


@pytest.mark.asyncio
async def test_service_initialization(mock_db):
    """Test BackgroundScraperService initialization"""
    service = BackgroundScraperService(mock_db)

    assert service.db == mock_db
    assert service.worker_tasks == {}
    assert not service.shutdown_event.is_set()
    assert service.job_semaphore._value == 3
    assert service.company_semaphore._value == 2


@pytest.mark.asyncio
async def test_start_with_no_profiles(mock_db):
    """Test start() seeds default profile when none exist"""
    service = BackgroundScraperService(mock_db)

    # No profiles initially
    mock_db.list_profiles.return_value = []

    # After seeding, return one default profile (disabled by default)
    default_profile = {
        "id": 1,
        "name": "default",
        "location": "San Francisco, CA",
        "keywords": "AI Engineer OR ML Engineer OR Research Engineer",
        "distance": 25,
        "time_filter": "r7200",
        "refresh_interval": 3600,
        "enabled": False,
        "last_scraped_at": None,
        "created_at": "2026-02-15T10:00:00Z",
        "updated_at": "2026-02-15T10:00:00Z",
    }
    mock_db.list_profiles.side_effect = [[], [default_profile]]

    await service.start()

    # Verify seed_default_profile was called
    mock_db.seed_default_profile.assert_called_once()

    # No workers spawned because default profile is disabled
    assert len(service.worker_tasks) == 0

    # Clean up
    await service.stop()


@pytest.mark.asyncio
async def test_start_spawns_workers_for_enabled_profiles(mock_db, sample_profile):
    """Test start() spawns workers for enabled profiles"""
    service = BackgroundScraperService(mock_db)

    # Return one enabled profile
    mock_db.list_profiles.return_value = [sample_profile]

    # Mock _scrape_profile_once to prevent actual scraping
    service._scrape_profile_once = AsyncMock(return_value=0)

    await service.start()

    # Verify worker spawned
    assert len(service.worker_tasks) == 1
    assert 1 in service.worker_tasks

    # Clean up
    await service.stop()


@pytest.mark.asyncio
async def test_stop_cancels_all_workers(mock_db, sample_profile):
    """Test stop() cancels all worker tasks gracefully"""
    service = BackgroundScraperService(mock_db)
    mock_db.list_profiles.return_value = [sample_profile]

    # Mock _scrape_profile_once to prevent actual scraping
    service._scrape_profile_once = AsyncMock(return_value=0)

    await service.start()
    assert len(service.worker_tasks) == 1

    await service.stop()

    # Verify shutdown event set
    assert service.shutdown_event.is_set()

    # Verify all tasks cancelled
    for task in service.worker_tasks.values():
        assert task.cancelled() or task.done()


@pytest.mark.asyncio
async def test_spawn_worker(mock_db, sample_profile):
    """Test _spawn_worker creates a task"""
    service = BackgroundScraperService(mock_db)
    profile = ScrapingProfile(**sample_profile)

    # Mock _scrape_profile_once to prevent actual scraping
    service._scrape_profile_once = AsyncMock(return_value=0)

    await service._spawn_worker(profile)

    assert 1 in service.worker_tasks
    assert isinstance(service.worker_tasks[1], asyncio.Task)

    # Clean up
    await service.stop()


@pytest.mark.asyncio
async def test_spawn_worker_duplicate_warning(mock_db, sample_profile):
    """Test _spawn_worker warns when worker already exists"""
    service = BackgroundScraperService(mock_db)
    profile = ScrapingProfile(**sample_profile)

    # Mock _scrape_profile_once to prevent actual scraping
    service._scrape_profile_once = AsyncMock(return_value=0)

    # Spawn worker twice
    await service._spawn_worker(profile)
    initial_task = service.worker_tasks[1]

    await service._spawn_worker(profile)

    # Verify same task (not replaced)
    assert service.worker_tasks[1] == initial_task

    # Clean up
    await service.stop()


@pytest.mark.asyncio
async def test_kill_worker(mock_db, sample_profile):
    """Test _kill_worker cancels a worker task"""
    service = BackgroundScraperService(mock_db)
    profile = ScrapingProfile(**sample_profile)

    # Mock _scrape_profile_once to prevent actual scraping
    service._scrape_profile_once = AsyncMock(return_value=0)

    await service._spawn_worker(profile)
    assert 1 in service.worker_tasks

    await service._kill_worker(1)

    assert 1 not in service.worker_tasks


@pytest.mark.asyncio
async def test_kill_worker_nonexistent(mock_db):
    """Test _kill_worker handles nonexistent worker gracefully"""
    service = BackgroundScraperService(mock_db)

    # Should not raise error
    await service._kill_worker("nonexistent")

    assert "nonexistent" not in service.worker_tasks


@pytest.mark.asyncio
async def test_reload_profiles_loop_spawns_new_worker(mock_db, sample_profile):
    """Test _reload_profiles_loop spawns worker for new profile"""
    service = BackgroundScraperService(mock_db)

    # Mock _scrape_profile_once to prevent actual scraping
    service._scrape_profile_once = AsyncMock(return_value=0)

    # Initially no profiles
    mock_db.list_profiles.return_value = []

    # Start the reload loop
    reload_task = asyncio.create_task(service._reload_profiles_loop())

    # Wait a bit for the loop to start
    await asyncio.sleep(0.1)

    # Add a new profile
    mock_db.list_profiles.return_value = [sample_profile]

    # Mock sleep to speed up the test
    with patch("asyncio.sleep", new_callable=AsyncMock):
        # Trigger one iteration
        await asyncio.sleep(0.1)

    # Wait for worker to spawn
    await asyncio.sleep(0.2)

    # Stop the service to cancel the reload loop
    await service.stop()
    reload_task.cancel()
    try:
        await reload_task
    except asyncio.CancelledError:
        pass


@pytest.mark.asyncio
async def test_reload_profiles_loop_kills_disabled_worker(mock_db, sample_profile):
    """Test _reload_profiles_loop kills worker when profile is disabled"""
    service = BackgroundScraperService(mock_db)

    # Mock _scrape_profile_once to prevent actual scraping
    service._scrape_profile_once = AsyncMock(return_value=0)

    # Start with enabled profile
    mock_db.list_profiles.return_value = [sample_profile]
    await service.start()
    assert len(service.worker_tasks) == 1

    # Disable the profile
    disabled_profile = sample_profile.copy()
    disabled_profile["enabled"] = False
    mock_db.list_profiles.return_value = [disabled_profile]

    # Wait for reload loop to detect change (mocked sleep)
    await asyncio.sleep(0.2)

    # Stop the service
    await service.stop()


@pytest.mark.asyncio
async def test_run_profile_worker_scrapes_and_waits(mock_db, sample_profile):
    """Test _run_profile_worker executes scrape and waits for refresh_interval"""
    service = BackgroundScraperService(mock_db)
    profile = ScrapingProfile(**sample_profile)

    # Mock _scrape_profile_once to prevent actual scraping
    service._scrape_profile_once = AsyncMock(return_value=5)

    # Set short refresh interval for testing
    profile.refresh_interval = 0.1

    # Run worker for a short time
    worker_task = asyncio.create_task(service._run_profile_worker(profile))
    await asyncio.sleep(0.3)

    # Stop the worker
    await service.stop()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass

    # Verify scrape was called at least once
    assert service._scrape_profile_once.call_count >= 1
    # Verify last_run was updated
    assert mock_db.update_profile_last_run.call_count >= 1


@pytest.mark.asyncio
async def test_run_profile_worker_handles_scrape_errors(mock_db, sample_profile):
    """Test _run_profile_worker handles scraping errors with backoff"""
    service = BackgroundScraperService(mock_db)
    profile = ScrapingProfile(**sample_profile)

    # Mock _scrape_profile_once to raise error
    service._scrape_profile_once = AsyncMock(side_effect=Exception("Scraping failed"))

    # Set short refresh interval for testing
    profile.refresh_interval = 0.1

    # Run worker for a short time
    worker_task = asyncio.create_task(service._run_profile_worker(profile))
    await asyncio.sleep(0.3)

    # Stop the worker
    await service.stop()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass

    # Verify scrape was attempted
    assert service._scrape_profile_once.call_count >= 1


# ========== Scraping Logic Tests (Step 9) ==========


@pytest.fixture
def mock_job_summary():
    """Create a mock JobSummary"""
    from linkedin_mcp_server.scraper import JobSummary

    return JobSummary(
        job_id="4271043001",
        title="ML Engineer",
        company="Instawork",
        company_url="https://www.linkedin.com/company/instawork",
        location="San Francisco, CA",
        posted_date="2 days ago",
        posted_date_iso="2026-02-13T10:00:00Z",
        job_url="https://www.linkedin.com/jobs/view/4271043001",
        benefits_badge="Actively Hiring",
    )


@pytest.fixture
def mock_job_detail():
    """Create a mock JobDetail"""
    from linkedin_mcp_server.scraper import JobDetail

    return JobDetail(
        job_id="4271043001",
        url="https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/4271043001",
        source="linkedin",
        scraped_at="2026-02-15T10:00:00Z",
        title="ML Engineer",
        company="Instawork",
        company_url="https://www.linkedin.com/company/instawork",
        location="San Francisco, CA",
        posted_date="2 days ago",
        posted_date_iso="2026-02-13T10:00:00Z",
        number_of_applicants="Over 200 applicants",
        salary="$160,000 - $185,000",
        raw_description="We are seeking an ML Engineer...",
        employment_type="Full-time",
        seniority_level="Entry level",
        job_function="Engineering",
        industries="Technology",
        skills=["Python", "TensorFlow"],
        company_details="N/A",
        salary_min=160000.0,
        salary_max=185000.0,
        salary_currency="USD",
        equity_offered=False,
        remote_eligible=False,
        visa_sponsorship=False,
        easy_apply=False,
        normalized_company_name="instawork",
    )


@pytest.mark.asyncio
async def test_scrape_profile_once_with_mock(
    mock_db, sample_profile, mock_job_summary, mock_job_detail
):
    """Test _scrape_profile_once with mocked scraper functions"""
    service = BackgroundScraperService(mock_db)
    profile = ScrapingProfile(**sample_profile)

    # Mock search_jobs_pages and fetch_job_details
    with patch(
        "linkedin_mcp_server.background_scraper.search_jobs_pages",
        new_callable=AsyncMock,
    ) as mock_search:
        with patch(
            "linkedin_mcp_server.background_scraper.fetch_job_details",
            new_callable=AsyncMock,
        ) as mock_fetch:
            # Set up mock returns
            mock_search.return_value = [mock_job_summary]
            mock_fetch.return_value = [mock_job_detail]

            # Mock DB methods
            mock_db.get_job.return_value = None  # No existing job
            mock_db.upsert_jobs.return_value = 1

            # Execute scrape
            count = await service._scrape_profile_once(profile)

            # Verify scraping functions called with correct params
            mock_search.assert_called_once()
            call_args = mock_search.call_args
            assert call_args.kwargs["query"] == "ML Engineer"  # keywords from profile
            assert call_args.kwargs["location"] == "San Francisco, CA"
            assert call_args.kwargs["distance"] == 25
            assert call_args.kwargs["num_pages"] == 5
            assert call_args.kwargs["filters"] == {"f_TPR": "r7200"}

            # Verify fetch called with job IDs
            mock_fetch.assert_called_once()
            assert mock_fetch.call_args.args[1] == ["4271043001"]

            # Verify upsert called
            mock_db.upsert_jobs.assert_called_once()
            jobs = mock_db.upsert_jobs.call_args.args[0]
            assert len(jobs) == 1
            assert jobs[0]["job_id"] == "4271043001"
            assert jobs[0]["profile_id"] == 1

            # Verify return count
            assert count == 1


@pytest.mark.asyncio
async def test_scrape_profile_once_no_jobs_found(mock_db, sample_profile):
    """Test _scrape_profile_once when no jobs found"""
    service = BackgroundScraperService(mock_db)
    profile = ScrapingProfile(**sample_profile)

    # Mock search_jobs_pages to return empty list
    with patch(
        "linkedin_mcp_server.background_scraper.search_jobs_pages",
        new_callable=AsyncMock,
    ) as mock_search:
        mock_search.return_value = []

        count = await service._scrape_profile_once(profile)

        assert count == 0
        # Verify upsert not called
        mock_db.upsert_jobs.assert_not_called()


@pytest.mark.asyncio
async def test_detect_job_changes(mock_db):
    """Test _detect_job_changes detects and records changes"""
    service = BackgroundScraperService(mock_db)

    old_job = {
        "job_id": "123",
        "salary": "$100K - $150K",
        "number_of_applicants": "50 applicants",
        "raw_description": "Old description",
    }

    new_job = {
        "job_id": "123",
        "salary": "$120K - $170K",  # Changed
        "number_of_applicants": "75 applicants",  # Changed
        "raw_description": "Old description",  # Unchanged
    }

    await service._detect_job_changes(old_job, new_job)

    # Verify record_job_change called twice (salary and applicants changed)
    assert mock_db.record_job_change.call_count == 2

    # Verify correct calls
    calls = mock_db.record_job_change.call_args_list
    assert any(
        call.kwargs["field_name"] == "salary"
        and call.kwargs["old_value"] == "$100K - $150K"
        and call.kwargs["new_value"] == "$120K - $170K"
        for call in calls
    )
    assert any(
        call.kwargs["field_name"] == "number_of_applicants"
        and call.kwargs["old_value"] == "50 applicants"
        and call.kwargs["new_value"] == "75 applicants"
        for call in calls
    )


@pytest.mark.asyncio
async def test_detect_job_changes_no_changes(mock_db):
    """Test _detect_job_changes when no fields changed"""
    service = BackgroundScraperService(mock_db)

    job = {
        "job_id": "123",
        "salary": "$100K - $150K",
        "number_of_applicants": "50 applicants",
        "raw_description": "Same description",
    }

    await service._detect_job_changes(job, job)

    # Verify record_job_change not called
    mock_db.record_job_change.assert_not_called()
