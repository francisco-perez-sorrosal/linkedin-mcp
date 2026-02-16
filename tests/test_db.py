"""
Tests for database schema and connection lifecycle.
"""

import sqlite3
import tempfile
from pathlib import Path
import pytest
from linkedin_mcp_server.db import JobDatabase, normalize_company_name


def test_normalize_company_name():
    """Test company name normalization removes common suffixes."""
    assert normalize_company_name("Anthropic, Inc.") == "anthropic"
    assert normalize_company_name("Google LLC") == "google"
    assert normalize_company_name("Microsoft Corporation") == "microsoft"
    assert normalize_company_name("OpenAI") == "openai"
    assert normalize_company_name("Meta, Inc.") == "meta"
    assert normalize_company_name("Amazon.com, Inc.") == "amazon.com"


def test_initialize_schema():
    """Test database schema creation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = JobDatabase(db_path)

        # Initialize schema
        db.initialize_schema()

        # Verify tables exist
        cursor = db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [row[0] for row in cursor.fetchall()]

        expected_tables = [
            "applications",
            "company_enrichment",
            "job_changes",
            "jobs",
            "jobs_fts",
            "jobs_fts_config",
            "jobs_fts_content",
            "jobs_fts_data",
            "jobs_fts_docsize",
            "jobs_fts_idx",
            "profiles",
        ]

        # FTS5 creates additional internal tables
        for table in ["applications", "company_enrichment", "job_changes", "jobs", "jobs_fts", "profiles"]:
            assert table in tables, f"Table {table} not found"

        # Verify WAL mode enabled
        cursor = db.conn.execute("PRAGMA journal_mode")
        journal_mode = cursor.fetchone()[0]
        assert journal_mode.lower() == "wal", f"Expected WAL mode, got {journal_mode}"

        # Verify foreign keys enabled
        cursor = db.conn.execute("PRAGMA foreign_keys")
        fk_enabled = cursor.fetchone()[0]
        assert fk_enabled == 1, "Foreign keys not enabled"

        db.close()


def test_initialize_schema_idempotent():
    """Test that initialize_schema() can be called multiple times without errors."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = JobDatabase(db_path)

        # Call initialize_schema() twice
        db.initialize_schema()
        db.initialize_schema()  # Should not raise

        # Verify database still works
        cursor = db.conn.execute("SELECT COUNT(*) FROM jobs")
        count = cursor.fetchone()[0]
        assert count == 0

        db.close()


def test_context_manager():
    """Test database context manager."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"

        with JobDatabase(db_path) as db:
            db.initialize_schema()

            # Verify database works inside context
            cursor = db.conn.execute("SELECT COUNT(*) FROM jobs")
            count = cursor.fetchone()[0]
            assert count == 0

        # Verify connection closed after context
        # Attempting to use connection should fail
        with pytest.raises(sqlite3.ProgrammingError):
            db.conn.execute("SELECT COUNT(*) FROM jobs")


def test_indexes_created():
    """Test that all indexes are created."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = JobDatabase(db_path)
        db.initialize_schema()

        # Get all indexes
        cursor = db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' ORDER BY name"
        )
        indexes = [row[0] for row in cursor.fetchall()]

        expected_indexes = [
            "idx_jobs_company",
            "idx_jobs_location",
            "idx_jobs_posted_date",
            "idx_jobs_scraped_at",
            "idx_jobs_remote",
            "idx_jobs_visa",
            "idx_jobs_profile",
            "idx_applications_job_id",
            "idx_applications_status",
            "idx_company_normalized",
            "idx_company_refresh",
        ]

        for index in expected_indexes:
            assert index in indexes, f"Index {index} not found"

        db.close()


def test_fts5_triggers_created():
    """Test that FTS5 sync triggers are created."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = JobDatabase(db_path)
        db.initialize_schema()

        # Get all triggers
        cursor = db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' ORDER BY name"
        )
        triggers = [row[0] for row in cursor.fetchall()]

        expected_triggers = [
            "jobs_fts_delete",
            "jobs_fts_insert",
            "jobs_fts_update",
        ]

        for trigger in expected_triggers:
            assert trigger in triggers, f"Trigger {trigger} not found"

        db.close()


# ========== CRUD Operation Tests (Step 2) ==========

def test_upsert_jobs_insert():
    """Test inserting new jobs."""
    from datetime import datetime, timezone

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = JobDatabase(db_path)
        db.initialize_schema()

        # Create test jobs
        jobs = [
            {
                "job_id": "123",
                "title": "ML Engineer",
                "company": "Anthropic, Inc.",
                "location": "San Francisco, CA",
                "posted_date": "2026-02-15",
                "posted_date_iso": "2026-02-15T10:00:00Z",
                "scraped_at": datetime.now(timezone.utc).isoformat(),
            },
            {
                "job_id": "456",
                "title": "Data Scientist",
                "company": "Google LLC",
                "location": "Mountain View, CA",
                "posted_date": "2026-02-14",
                "posted_date_iso": "2026-02-14T14:00:00Z",
                "scraped_at": datetime.now(timezone.utc).isoformat(),
            },
        ]

        count = db.upsert_jobs(jobs)
        assert count == 2

        # Verify jobs exist
        cursor = db.conn.execute("SELECT COUNT(*) FROM jobs")
        assert cursor.fetchone()[0] == 2

        # Verify company name normalization
        job = db.get_job("123")
        assert job["normalized_company_name"] == "anthropic"

        db.close()


def test_upsert_jobs_update():
    """Test updating existing jobs (no duplicates)."""
    from datetime import datetime, timezone

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = JobDatabase(db_path)
        db.initialize_schema()

        # Insert job
        job = {
            "job_id": "123",
            "title": "ML Engineer",
            "company": "Anthropic",
            "location": "San Francisco, CA",
            "posted_date": "2026-02-15",
            "posted_date_iso": "2026-02-15T10:00:00Z",
            "scraped_at": datetime.now(timezone.utc).isoformat(),
        }
        db.upsert_jobs([job])

        # Update same job with different title
        job["title"] = "Senior ML Engineer"
        db.upsert_jobs([job])

        # Verify no duplicate (still 1 job)
        cursor = db.conn.execute("SELECT COUNT(*) FROM jobs")
        assert cursor.fetchone()[0] == 1

        # Verify title updated
        updated_job = db.get_job("123")
        assert updated_job["title"] == "Senior ML Engineer"

        db.close()


def test_get_job():
    """Test retrieving a single job by ID."""
    from datetime import datetime, timezone

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = JobDatabase(db_path)
        db.initialize_schema()

        job = {
            "job_id": "123",
            "title": "ML Engineer",
            "company": "Anthropic",
            "location": "San Francisco, CA",
            "posted_date": "2026-02-15",
            "posted_date_iso": "2026-02-15T10:00:00Z",
            "scraped_at": datetime.now(timezone.utc).isoformat(),
        }
        db.upsert_jobs([job])

        # Get existing job
        fetched = db.get_job("123")
        assert fetched is not None
        assert fetched["job_id"] == "123"
        assert fetched["title"] == "ML Engineer"

        # Get non-existent job
        missing = db.get_job("999")
        assert missing is None

        db.close()


def test_query_jobs_no_filters():
    """Test querying all jobs without filters."""
    from datetime import datetime, timezone

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = JobDatabase(db_path)
        db.initialize_schema()

        jobs = [
            {
                "job_id": str(i),
                "title": f"Job {i}",
                "company": "Test Co",
                "location": "San Francisco, CA",
                "posted_date": "2026-02-15",
                "posted_date_iso": f"2026-02-15T{i:02d}:00:00Z",
                "scraped_at": datetime.now(timezone.utc).isoformat(),
            }
            for i in range(30)
        ]
        db.upsert_jobs(jobs)

        # Query with default limit
        results = db.query_jobs(limit=20, offset=0)
        assert len(results) == 20

        # Query with pagination
        results_page2 = db.query_jobs(limit=20, offset=20)
        assert len(results_page2) == 10

        db.close()


def test_query_jobs_company_filter():
    """Test filtering by company name."""
    from datetime import datetime, timezone

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = JobDatabase(db_path)
        db.initialize_schema()

        jobs = [
            {
                "job_id": "1",
                "title": "Job 1",
                "company": "Anthropic, Inc.",
                "location": "San Francisco, CA",
                "posted_date": "2026-02-15",
                "posted_date_iso": "2026-02-15T10:00:00Z",
                "scraped_at": datetime.now(timezone.utc).isoformat(),
            },
            {
                "job_id": "2",
                "title": "Job 2",
                "company": "Google LLC",
                "location": "Mountain View, CA",
                "posted_date": "2026-02-15",
                "posted_date_iso": "2026-02-15T11:00:00Z",
                "scraped_at": datetime.now(timezone.utc).isoformat(),
            },
        ]
        db.upsert_jobs(jobs)

        # Filter by normalized company name
        results = db.query_jobs(company="Anthropic")
        assert len(results) == 1
        assert results[0]["company"] == "Anthropic, Inc."

        db.close()


def test_query_jobs_location_filter():
    """Test filtering by location."""
    from datetime import datetime, timezone

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = JobDatabase(db_path)
        db.initialize_schema()

        jobs = [
            {
                "job_id": "1",
                "title": "Job 1",
                "company": "Test Co",
                "location": "San Francisco, CA",
                "posted_date": "2026-02-15",
                "posted_date_iso": "2026-02-15T10:00:00Z",
                "scraped_at": datetime.now(timezone.utc).isoformat(),
            },
            {
                "job_id": "2",
                "title": "Job 2",
                "company": "Test Co",
                "location": "New York, NY",
                "posted_date": "2026-02-15",
                "posted_date_iso": "2026-02-15T11:00:00Z",
                "scraped_at": datetime.now(timezone.utc).isoformat(),
            },
        ]
        db.upsert_jobs(jobs)

        results = db.query_jobs(location="San Francisco")
        assert len(results) == 1
        assert results[0]["location"] == "San Francisco, CA"

        db.close()


def test_query_jobs_remote_filter():
    """Test filtering by remote eligibility."""
    from datetime import datetime, timezone

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = JobDatabase(db_path)
        db.initialize_schema()

        jobs = [
            {
                "job_id": "1",
                "title": "Remote Job",
                "company": "Test Co",
                "location": "San Francisco, CA",
                "posted_date": "2026-02-15",
                "posted_date_iso": "2026-02-15T10:00:00Z",
                "scraped_at": datetime.now(timezone.utc).isoformat(),
                "remote_eligible": 1,
            },
            {
                "job_id": "2",
                "title": "On-site Job",
                "company": "Test Co",
                "location": "New York, NY",
                "posted_date": "2026-02-15",
                "posted_date_iso": "2026-02-15T11:00:00Z",
                "scraped_at": datetime.now(timezone.utc).isoformat(),
                "remote_eligible": 0,
            },
        ]
        db.upsert_jobs(jobs)

        results = db.query_jobs(remote_only=True)
        assert len(results) == 1
        assert results[0]["title"] == "Remote Job"

        db.close()


def test_query_jobs_fts_search():
    """Test full-text search with FTS5."""
    from datetime import datetime, timezone

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = JobDatabase(db_path)
        db.initialize_schema()

        jobs = [
            {
                "job_id": "1",
                "title": "ML Engineer",
                "company": "Test Co",
                "location": "San Francisco, CA",
                "posted_date": "2026-02-15",
                "posted_date_iso": "2026-02-15T10:00:00Z",
                "scraped_at": datetime.now(timezone.utc).isoformat(),
                "raw_description": "Looking for machine learning expert with Python and TensorFlow experience",
            },
            {
                "job_id": "2",
                "title": "Frontend Developer",
                "company": "Test Co",
                "location": "New York, NY",
                "posted_date": "2026-02-15",
                "posted_date_iso": "2026-02-15T11:00:00Z",
                "scraped_at": datetime.now(timezone.utc).isoformat(),
                "raw_description": "React and TypeScript developer needed",
            },
        ]
        db.upsert_jobs(jobs)

        # Search for "machine learning"
        results = db.query_jobs(keywords="machine learning")
        assert len(results) == 1
        assert results[0]["job_id"] == "1"

        # Search for "Python"
        results = db.query_jobs(keywords="Python")
        assert len(results) == 1
        assert results[0]["job_id"] == "1"

        db.close()


def test_fts_survives_upsert():
    """Test FTS5 index stays consistent after INSERT OR REPLACE (upsert).

    This was the root cause of the FTS corruption: external content FTS5
    requires the special 'delete' command in triggers, not regular DELETE.
    """
    from datetime import datetime, timezone

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = JobDatabase(db_path)
        db.initialize_schema()

        now = datetime.now(timezone.utc).isoformat()

        # Insert job with description about Python
        job = {
            "job_id": "42",
            "title": "ML Engineer",
            "company": "Acme Corp",
            "location": "SF",
            "posted_date": "2026-02-15",
            "posted_date_iso": "2026-02-15T10:00:00Z",
            "scraped_at": now,
            "raw_description": "Expert in Python and TensorFlow required",
        }
        db.upsert_jobs([job])

        # FTS search should find by old description
        results = db.query_jobs(keywords="Python")
        assert len(results) == 1
        assert results[0]["job_id"] == "42"

        # Upsert same job with different description (triggers INSERT OR REPLACE)
        job["raw_description"] = "Expert in Rust and CUDA required"
        db.upsert_jobs([job])

        # FTS should find by new description
        results = db.query_jobs(keywords="Rust")
        assert len(results) == 1
        assert results[0]["job_id"] == "42"

        # FTS should NOT find by old description
        results = db.query_jobs(keywords="Python")
        assert len(results) == 0

        # Still only one job in the table
        assert db.count_jobs() == 1

        db.close()


def test_rebuild_fts():
    """Test manual FTS5 index rebuild."""
    from datetime import datetime, timezone

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = JobDatabase(db_path)
        db.initialize_schema()

        now = datetime.now(timezone.utc).isoformat()

        jobs = [
            {
                "job_id": "1",
                "title": "ML Engineer",
                "company": "Test Co",
                "location": "SF",
                "posted_date": "2026-02-15",
                "posted_date_iso": "2026-02-15T10:00:00Z",
                "scraped_at": now,
                "raw_description": "Machine learning and deep learning",
            },
            {
                "job_id": "2",
                "title": "Frontend Dev",
                "company": "Test Co",
                "location": "SF",
                "posted_date": "2026-02-15",
                "posted_date_iso": "2026-02-15T11:00:00Z",
                "scraped_at": now,
                "raw_description": "React and TypeScript expert",
            },
        ]
        db.upsert_jobs(jobs)

        # Rebuild should not raise and index should still work
        db.rebuild_fts()

        results = db.query_jobs(keywords="machine learning")
        assert len(results) == 1
        assert results[0]["job_id"] == "1"

        results = db.query_jobs(keywords="React")
        assert len(results) == 1
        assert results[0]["job_id"] == "2"

        db.close()


def test_query_jobs_sort_by():
    """Test sorting results."""
    from datetime import datetime, timezone, timedelta

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = JobDatabase(db_path)
        db.initialize_schema()

        now = datetime.now(timezone.utc)

        jobs = [
            {
                "job_id": "1",
                "title": "Job 1",
                "company": "Test Co",
                "location": "SF",
                "posted_date": "2026-02-13",
                "posted_date_iso": (now - timedelta(days=2)).isoformat(),
                "scraped_at": (now - timedelta(hours=5)).isoformat(),
            },
            {
                "job_id": "2",
                "title": "Job 2",
                "company": "Test Co",
                "location": "SF",
                "posted_date": "2026-02-15",
                "posted_date_iso": now.isoformat(),
                "scraped_at": (now - timedelta(hours=1)).isoformat(),
            },
        ]
        db.upsert_jobs(jobs)

        # Sort by posted_date DESC (newest first)
        results = db.query_jobs(sort_by="posted_date")
        assert results[0]["job_id"] == "2"

        # Sort by scraped_at DESC (most recent scrape first)
        results = db.query_jobs(sort_by="scraped_at")
        assert results[0]["job_id"] == "2"

        db.close()


def test_count_jobs():
    """Test counting jobs with filters."""
    from datetime import datetime, timezone

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = JobDatabase(db_path)
        db.initialize_schema()

        jobs = [
            {
                "job_id": str(i),
                "title": f"Job {i}",
                "company": "Anthropic" if i % 2 == 0 else "Google",
                "location": "San Francisco, CA",
                "posted_date": "2026-02-15",
                "posted_date_iso": "2026-02-15T10:00:00Z",
                "scraped_at": datetime.now(timezone.utc).isoformat(),
                "remote_eligible": 1 if i % 3 == 0 else 0,
            }
            for i in range(10)
        ]
        db.upsert_jobs(jobs)

        # Count all jobs
        total = db.count_jobs()
        assert total == 10

        # Count by company
        anthropic_count = db.count_jobs(company="Anthropic")
        assert anthropic_count == 5

        # Count remote jobs
        remote_count = db.count_jobs(remote_only=True)
        assert remote_count in [3, 4]  # Divisible by 3 in range 0-9

        db.close()


def test_delete_old_jobs():
    """Test deleting old jobs."""
    from datetime import datetime, timezone, timedelta

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = JobDatabase(db_path)
        db.initialize_schema()

        now = datetime.now(timezone.utc)

        jobs = [
            {
                "job_id": "old1",
                "title": "Old Job 1",
                "company": "Test Co",
                "location": "SF",
                "posted_date": "2026-02-01",
                "posted_date_iso": (now - timedelta(days=14)).isoformat(),
                "scraped_at": (now - timedelta(days=14)).isoformat(),
            },
            {
                "job_id": "recent1",
                "title": "Recent Job 1",
                "company": "Test Co",
                "location": "SF",
                "posted_date": "2026-02-15",
                "posted_date_iso": now.isoformat(),
                "scraped_at": now.isoformat(),
            },
        ]
        db.upsert_jobs(jobs)

        # Delete jobs older than 7 days
        deleted = db.delete_old_jobs(max_age_seconds=7 * 24 * 3600)
        assert deleted == 1

        # Verify only recent job remains
        remaining = db.query_jobs()
        assert len(remaining) == 1
        assert remaining[0]["job_id"] == "recent1"

        db.close()


# ========== Profile CRUD Tests (Step 3) ==========

def test_upsert_profile_insert():
    """Test creating a new profile."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = JobDatabase(db_path)
        db.initialize_schema()

        profile = {
            "name": "test_profile",
            "location": "San Francisco, CA",
            "keywords": "ML Engineer",
            "distance": 25,
            "time_filter": "r7200",
            "refresh_interval": 3600,
        }

        profile_id = db.upsert_profile(profile)
        assert profile_id > 0

        # Verify profile exists
        fetched = db.get_profile(profile_id)
        assert fetched is not None
        assert fetched["name"] == "test_profile"
        assert fetched["location"] == "San Francisco, CA"

        db.close()


def test_upsert_profile_update():
    """Test updating an existing profile."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = JobDatabase(db_path)
        db.initialize_schema()

        profile = {
            "name": "test_profile",
            "location": "San Francisco, CA",
            "keywords": "ML Engineer",
        }

        profile_id = db.upsert_profile(profile)

        # Update same profile
        profile["keywords"] = "AI Engineer"
        updated_id = db.upsert_profile(profile)

        # Should return same ID
        assert updated_id == profile_id

        # Verify keywords updated
        fetched = db.get_profile(profile_id)
        assert fetched["keywords"] == "AI Engineer"

        db.close()


def test_list_profiles():
    """Test listing profiles with enabled filter."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = JobDatabase(db_path)
        db.initialize_schema()

        # Create enabled profile
        db.upsert_profile({
            "name": "enabled_profile",
            "location": "SF",
            "keywords": "test",
            "enabled": 1,
        })

        # Create disabled profile
        profile_id = db.upsert_profile({
            "name": "disabled_profile",
            "location": "SF",
            "keywords": "test",
            "enabled": 0,
        })

        # List enabled only
        enabled_profiles = db.list_profiles(enabled_only=True)
        assert len(enabled_profiles) == 1
        assert enabled_profiles[0]["name"] == "enabled_profile"

        # List all
        all_profiles = db.list_profiles(enabled_only=False)
        assert len(all_profiles) == 2

        db.close()


def test_delete_profile_soft():
    """Test soft deleting a profile."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = JobDatabase(db_path)
        db.initialize_schema()

        profile_id = db.upsert_profile({
            "name": "test",
            "location": "SF",
            "keywords": "test",
        })

        # Soft delete
        db.delete_profile(profile_id, hard_delete=False)

        # Verify still exists but disabled
        profile = db.get_profile(profile_id)
        assert profile is not None
        assert profile["enabled"] == 0

        db.close()


def test_delete_profile_hard():
    """Test hard deleting a profile."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = JobDatabase(db_path)
        db.initialize_schema()

        profile_id = db.upsert_profile({
            "name": "test",
            "location": "SF",
            "keywords": "test",
        })

        # Hard delete
        db.delete_profile(profile_id, hard_delete=True)

        # Verify doesn't exist
        profile = db.get_profile(profile_id)
        assert profile is None

        db.close()


def test_update_profile_last_run():
    """Test updating profile last_scraped_at timestamp."""
    from datetime import datetime, timezone

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = JobDatabase(db_path)
        db.initialize_schema()

        profile_id = db.upsert_profile({
            "name": "test",
            "location": "SF",
            "keywords": "test",
        })

        timestamp = datetime.now(timezone.utc).isoformat()
        db.update_profile_last_run(profile_id, timestamp)

        profile = db.get_profile(profile_id)
        assert profile["last_scraped_at"] == timestamp

        db.close()


def test_seed_default_profile():
    """Test seeding default profile."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = JobDatabase(db_path)
        db.initialize_schema()

        # Seed default profile
        profile_id = db.seed_default_profile()
        assert profile_id is not None

        # Verify default profile created
        profile = db.get_profile(profile_id)
        assert profile["name"] == "default"
        assert profile["location"] == "San Francisco, CA"
        assert profile["keywords"] == "AI Engineer OR ML Engineer OR Research Engineer"

        # Seed again - should return None (idempotent)
        second_seed = db.seed_default_profile()
        assert second_seed is None

        db.close()


# ========== Application CRUD Tests (Step 3) ==========

def test_mark_job_applied():
    """Test marking a job as applied."""
    from datetime import datetime, timezone

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = JobDatabase(db_path)
        db.initialize_schema()

        # Create job
        job = {
            "job_id": "123",
            "title": "ML Engineer",
            "company": "Test Co",
            "location": "SF",
            "posted_date": "2026-02-15",
            "posted_date_iso": "2026-02-15T10:00:00Z",
            "scraped_at": datetime.now(timezone.utc).isoformat(),
        }
        db.upsert_jobs([job])

        # Mark as applied
        result = db.mark_job_applied("123", notes="Applied via LinkedIn")
        assert result is True

        # Verify application exists
        apps = db.list_applications()
        assert len(apps) == 1
        assert apps[0]["job_id"] == "123"
        assert apps[0]["status"] == "applied"
        assert apps[0]["notes"] == "Applied via LinkedIn"

        db.close()


def test_mark_job_applied_nonexistent():
    """Test marking a nonexistent job as applied."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = JobDatabase(db_path)
        db.initialize_schema()

        # Try to mark nonexistent job
        result = db.mark_job_applied("999")
        assert result is False

        db.close()


def test_update_application_status():
    """Test updating application status."""
    from datetime import datetime, timezone

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = JobDatabase(db_path)
        db.initialize_schema()

        # Create job and mark as applied
        job = {
            "job_id": "123",
            "title": "ML Engineer",
            "company": "Test Co",
            "location": "SF",
            "posted_date": "2026-02-15",
            "posted_date_iso": "2026-02-15T10:00:00Z",
            "scraped_at": datetime.now(timezone.utc).isoformat(),
        }
        db.upsert_jobs([job])
        db.mark_job_applied("123")

        # Update status
        result = db.update_application_status("123", "interviewing", notes="Phone screen scheduled")
        assert result is True

        # Verify status updated
        apps = db.list_applications()
        assert len(apps) == 1
        assert apps[0]["status"] == "interviewing"
        assert apps[0]["notes"] == "Phone screen scheduled"

        db.close()


def test_list_applications_filter_by_status():
    """Test filtering applications by status."""
    from datetime import datetime, timezone

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = JobDatabase(db_path)
        db.initialize_schema()

        # Create jobs
        jobs = [
            {
                "job_id": "1",
                "title": "Job 1",
                "company": "Test Co",
                "location": "SF",
                "posted_date": "2026-02-15",
                "posted_date_iso": "2026-02-15T10:00:00Z",
                "scraped_at": datetime.now(timezone.utc).isoformat(),
            },
            {
                "job_id": "2",
                "title": "Job 2",
                "company": "Test Co",
                "location": "SF",
                "posted_date": "2026-02-15",
                "posted_date_iso": "2026-02-15T11:00:00Z",
                "scraped_at": datetime.now(timezone.utc).isoformat(),
            },
        ]
        db.upsert_jobs(jobs)

        # Mark jobs with different statuses
        db.mark_job_applied("1")
        db.mark_job_applied("2")
        db.update_application_status("2", "interviewing")

        # Filter by status
        applied = db.list_applications(status="applied")
        assert len(applied) == 1
        assert applied[0]["job_id"] == "1"

        interviewing = db.list_applications(status="interviewing")
        assert len(interviewing) == 1
        assert interviewing[0]["job_id"] == "2"

        # List all
        all_apps = db.list_applications()
        assert len(all_apps) == 2

        db.close()


# ========== Company Enrichment Tests (Step 3) ==========

def test_upsert_company_enrichment():
    """Test inserting and updating company enrichment."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = JobDatabase(db_path)
        db.initialize_schema()

        company_data = {
            "company_name": "Anthropic, Inc.",
            "company_size": "51-200 employees",
            "company_industry": "AI",
            "company_description": "AI safety research",
            "company_specialties": ["AI", "Machine Learning"],
        }

        db.upsert_company_enrichment(company_data)

        # Verify company exists
        fetched = db.get_company_enrichment("Anthropic")
        assert fetched is not None
        assert fetched["company_size"] == "51-200 employees"
        assert fetched["company_specialties"] == ["AI", "Machine Learning"]

        # Update company
        company_data["company_size"] = "201-500 employees"
        db.upsert_company_enrichment(company_data)

        # Verify updated
        fetched = db.get_company_enrichment("Anthropic")
        assert fetched["company_size"] == "201-500 employees"

        db.close()


def test_get_companies_needing_refresh():
    """Test getting companies that need refresh."""
    from datetime import datetime, timezone, timedelta

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = JobDatabase(db_path)
        db.initialize_schema()

        # Insert company with old refresh date
        now = datetime.now(timezone.utc)
        old_company = {
            "company_name": "Old Company",
            "company_size": "100",
        }
        db.upsert_company_enrichment(old_company)

        # Manually set next_refresh_at to past
        db.conn.execute(
            "UPDATE company_enrichment SET next_refresh_at = ? WHERE company_name = ?",
            ((now - timedelta(days=1)).isoformat(), "Old Company")
        )
        db.conn.commit()

        # Insert company with future refresh date
        recent_company = {
            "company_name": "Recent Company",
            "company_size": "50",
        }
        db.upsert_company_enrichment(recent_company)

        # Get companies needing refresh
        companies = db.get_companies_needing_refresh()
        assert len(companies) == 1
        assert companies[0] == "Old Company"

        db.close()


# ========== Job Changes Tests (Step 3) ==========

def test_record_job_change():
    """Test recording a job change."""
    from datetime import datetime, timezone

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = JobDatabase(db_path)
        db.initialize_schema()

        # Create job first (foreign key constraint)
        job = {
            "job_id": "123",
            "title": "ML Engineer",
            "company": "Test Co",
            "location": "SF",
            "posted_date": "2026-02-15",
            "posted_date_iso": "2026-02-15T10:00:00Z",
            "scraped_at": datetime.now(timezone.utc).isoformat(),
        }
        db.upsert_jobs([job])

        # Record change
        db.record_job_change("123", "salary_max", "150000", "160000")

        # Verify change recorded
        cursor = db.conn.execute("SELECT * FROM job_changes WHERE job_id = ?", ("123",))
        row = cursor.fetchone()
        assert row is not None
        assert dict(row)["field_name"] == "salary_max"
        assert dict(row)["old_value"] == "150000"
        assert dict(row)["new_value"] == "160000"

        db.close()


def test_get_job_changes():
    """Test querying job changes."""
    from datetime import datetime, timezone, timedelta

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = JobDatabase(db_path)
        db.initialize_schema()

        # Create job
        job = {
            "job_id": "123",
            "title": "ML Engineer",
            "company": "Test Co",
            "location": "SF",
            "posted_date": "2026-02-15",
            "posted_date_iso": "2026-02-15T10:00:00Z",
            "scraped_at": datetime.now(timezone.utc).isoformat(),
        }
        db.upsert_jobs([job])

        # Record recent change
        db.record_job_change("123", "salary_max", "150000", "160000")

        # Record old change
        old_time = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        db.conn.execute(
            """
            INSERT INTO job_changes (job_id, changed_at, field_name, old_value, new_value)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("123", old_time, "salary_min", "120000", "130000")
        )
        db.conn.commit()

        # Get changes from last 24 hours
        changes = db.get_job_changes(since_hours=24)
        assert len(changes) == 1
        assert changes[0]["field_name"] == "salary_max"

        # Get changes from last 3 days
        changes = db.get_job_changes(since_hours=72)
        assert len(changes) == 2

        db.close()


# ========== Analytics Tests (Step 4) ==========

def test_get_cache_analytics_empty():
    """Test analytics with empty database."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = JobDatabase(db_path)
        db.initialize_schema()

        analytics = db.get_cache_analytics()

        # Verify structure
        assert "jobs" in analytics
        assert "scraping_profiles" in analytics
        assert "applications" in analytics
        assert "company_enrichment" in analytics
        assert "cache_health" in analytics

        # Verify empty counts
        assert analytics["jobs"]["total"] == 0
        assert analytics["applications"]["total"] == 0
        assert analytics["company_enrichment"]["total"] == 0

        db.close()


def test_get_cache_analytics_populated():
    """Test analytics with populated database."""
    from datetime import datetime, timezone, timedelta

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = JobDatabase(db_path)
        db.initialize_schema()

        now = datetime.now(timezone.utc)

        # Create jobs with different ages
        jobs = [
            {
                "job_id": "fresh1",
                "title": "Fresh Job",
                "company": "Anthropic",
                "location": "San Francisco, CA",
                "posted_date": "2026-02-15",
                "posted_date_iso": now.isoformat(),
                "scraped_at": (now - timedelta(hours=1)).isoformat(),  # Fresh (24h)
            },
            {
                "job_id": "recent1",
                "title": "Recent Job",
                "company": "Google",
                "location": "Mountain View, CA",
                "posted_date": "2026-02-10",
                "posted_date_iso": (now - timedelta(days=5)).isoformat(),
                "scraped_at": (now - timedelta(days=5)).isoformat(),  # Recent (7d)
            },
            {
                "job_id": "old1",
                "title": "Old Job",
                "company": "Meta",
                "location": "Menlo Park, CA",
                "posted_date": "2026-01-20",
                "posted_date_iso": (now - timedelta(days=20)).isoformat(),
                "scraped_at": (now - timedelta(days=20)).isoformat(),  # Old (30d)
            },
        ]
        db.upsert_jobs(jobs)

        # Create profile
        profile_id = db.seed_default_profile()
        db.update_profile_last_run(profile_id, (now - timedelta(hours=1)).isoformat())

        # Mark one job as applied
        db.mark_job_applied("fresh1")

        # Add company enrichment
        db.upsert_company_enrichment({
            "company_name": "Anthropic",
            "company_size": "51-200",
        })

        # Get analytics
        analytics = db.get_cache_analytics()

        # Verify job analytics
        assert analytics["jobs"]["total"] == 3
        assert analytics["jobs"]["by_age"]["fresh_24h"] == 1
        assert analytics["jobs"]["by_age"]["recent_7d"] == 2
        assert analytics["jobs"]["by_age"]["old_30d"] == 3
        assert analytics["jobs"]["by_age"]["stale"] == 0

        # Verify application status
        assert analytics["jobs"]["by_application_status"]["not_applied"] == 2
        assert analytics["jobs"]["by_application_status"]["applied"] == 1

        # Verify top companies
        assert len(analytics["jobs"]["top_companies"]) == 3
        assert analytics["jobs"]["top_companies"][0]["company"] == "Anthropic"

        # Verify top locations
        assert len(analytics["jobs"]["top_locations"]) == 3

        # Verify profiles
        assert len(analytics["scraping_profiles"]) == 1
        assert analytics["scraping_profiles"][0]["name"] == "default"
        assert analytics["scraping_profiles"][0]["enabled"] is True

        # Verify applications
        assert analytics["applications"]["total"] == 1
        assert analytics["applications"]["applied"] == 1

        # Verify company enrichment
        assert analytics["company_enrichment"]["total"] == 1

        # Verify cache health
        assert analytics["cache_health"]["size_mb"] >= 0  # May be 0 in test environment
        assert analytics["cache_health"]["oldest_job"] is not None
        assert analytics["cache_health"]["newest_job"] is not None

        db.close()


def test_analytics_by_age_buckets():
    """Test job age bucket counts."""
    from datetime import datetime, timezone, timedelta

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = JobDatabase(db_path)
        db.initialize_schema()

        now = datetime.now(timezone.utc)

        jobs = [
            # Fresh (< 24h)
            {
                "job_id": "1",
                "title": "Job 1",
                "company": "A",
                "location": "SF",
                "posted_date": "2026-02-15",
                "posted_date_iso": now.isoformat(),
                "scraped_at": (now - timedelta(hours=12)).isoformat(),
            },
            # Recent (< 7d)
            {
                "job_id": "2",
                "title": "Job 2",
                "company": "A",
                "location": "SF",
                "posted_date": "2026-02-10",
                "posted_date_iso": now.isoformat(),
                "scraped_at": (now - timedelta(days=3)).isoformat(),
            },
            # Old (< 30d)
            {
                "job_id": "3",
                "title": "Job 3",
                "company": "A",
                "location": "SF",
                "posted_date": "2026-01-20",
                "posted_date_iso": now.isoformat(),
                "scraped_at": (now - timedelta(days=15)).isoformat(),
            },
            # Stale (> 30d)
            {
                "job_id": "4",
                "title": "Job 4",
                "company": "A",
                "location": "SF",
                "posted_date": "2025-12-01",
                "posted_date_iso": now.isoformat(),
                "scraped_at": (now - timedelta(days=40)).isoformat(),
            },
        ]
        db.upsert_jobs(jobs)

        analytics = db.get_cache_analytics()

        assert analytics["jobs"]["by_age"]["fresh_24h"] == 1
        assert analytics["jobs"]["by_age"]["recent_7d"] == 2
        assert analytics["jobs"]["by_age"]["old_30d"] == 3
        assert analytics["jobs"]["by_age"]["stale"] == 1

        db.close()


def test_analytics_top_companies():
    """Test top companies ranking."""
    from datetime import datetime, timezone

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = JobDatabase(db_path)
        db.initialize_schema()

        now = datetime.now(timezone.utc)

        # Create jobs from different companies
        jobs = []
        companies = [
            ("Anthropic", 5),
            ("Google", 3),
            ("Meta", 2),
        ]

        for company, count in companies:
            for i in range(count):
                jobs.append({
                    "job_id": f"{company}_{i}",
                    "title": f"Job {i}",
                    "company": company,
                    "location": "SF",
                    "posted_date": "2026-02-15",
                    "posted_date_iso": now.isoformat(),
                    "scraped_at": now.isoformat(),
                })

        db.upsert_jobs(jobs)

        analytics = db.get_cache_analytics()

        # Verify top companies ordered by count
        top_companies = analytics["jobs"]["top_companies"]
        assert len(top_companies) == 3
        assert top_companies[0]["company"] == "Anthropic"
        assert top_companies[0]["count"] == 5
        assert top_companies[1]["company"] == "Google"
        assert top_companies[1]["count"] == 3
        assert top_companies[2]["company"] == "Meta"
        assert top_companies[2]["count"] == 2

        db.close()


def test_analytics_profile_next_scrape():
    """Test profile next_scrape_at computation."""
    from datetime import datetime, timezone, timedelta

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = JobDatabase(db_path)
        db.initialize_schema()

        # Create profile with last_scraped_at
        profile_id = db.upsert_profile({
            "name": "test",
            "location": "SF",
            "keywords": "ML",
            "refresh_interval": 7200,  # 2 hours
        })

        now = datetime.now(timezone.utc)
        last_scraped = now - timedelta(hours=1)
        db.update_profile_last_run(profile_id, last_scraped.isoformat())

        analytics = db.get_cache_analytics()

        profile = analytics["scraping_profiles"][0]
        assert profile["last_scraped_at"] == last_scraped.isoformat()

        # next_scrape_at should be last_scraped + refresh_interval
        expected_next = last_scraped + timedelta(seconds=7200)
        assert profile["next_scrape_at"] == expected_next.isoformat()

        db.close()
