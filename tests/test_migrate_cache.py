"""Tests for JSONL → SQLite migration"""

import json
from pathlib import Path
from datetime import datetime, timezone

import pytest

from linkedin_mcp_server.migrate_cache import migrate_jsonl_to_sqlite, transform_job_record
from linkedin_mcp_server.db import JobDatabase


def test_transform_job_record_basic():
    """Test basic job record transformation"""
    old_job = {
        "job_id": "123456",
        "title": "Senior ML Engineer",
        "company": "Anthropic, Inc.",
        "company_url": "https://anthropic.com",
        "location": "San Francisco, CA",
        "posted_date": "2 days ago",
        "scraped_at": "2026-02-15T10:00:00Z",
        "salary": "$150K - $200K",
        "raw_description": "We are hiring a remote ML engineer. Visa sponsorship available.",
        "employment_type": "Full-time",
        "seniority_level": "Mid-Senior level",
        "job_function": "Engineering",
        "industries": "Technology",
        "number_of_applicants": "50-100 applicants",
        "url": "https://linkedin.com/jobs/view/123456",
        "source": "linkedin"
    }

    new_job = transform_job_record(old_job)

    # Check core fields
    assert new_job["job_id"] == "123456"
    assert new_job["title"] == "Senior ML Engineer"
    assert new_job["company"] == "Anthropic, Inc."
    assert new_job["normalized_company_name"] == "anthropic"  # "Inc." removed, lowercase
    assert new_job["location"] == "San Francisco, CA"

    # Check enhanced fields
    assert new_job["salary_min"] == 150000.0
    assert new_job["salary_max"] == 200000.0
    assert new_job["salary_currency"] == "USD"
    assert new_job["remote_eligible"] is True
    assert new_job["visa_sponsorship"] is True

    # Check defaults
    assert new_job["easy_apply"] is False
    assert new_job["profile_id"] is None


def test_transform_job_record_missing_fields():
    """Test transformation with minimal fields"""
    old_job = {
        "job_id": "789",
        "title": "Engineer",
        "company": "Company",
    }

    new_job = transform_job_record(old_job)

    # Should have defaults
    assert new_job["job_id"] == "789"
    assert new_job["title"] == "Engineer"
    assert new_job["location"] == "N/A"
    assert new_job["salary_min"] is None
    assert new_job["salary_max"] is None
    assert new_job["remote_eligible"] is False
    assert new_job["visa_sponsorship"] is False


def test_transform_job_record_skills_extraction():
    """Test skills extraction from description"""
    old_job = {
        "job_id": "111",
        "title": "ML Engineer",
        "company": "Company",
        "raw_description": "Required skills: Python, TensorFlow, PyTorch, AWS"
    }

    new_job = transform_job_record(old_job)

    # Skills should be extracted and joined with commas (normalized to lowercase)
    skills_lower = new_job["skills"].lower()
    assert "python" in skills_lower
    assert "tensorflow" in skills_lower


def test_migrate_jsonl_to_sqlite_empty(tmp_path):
    """Test migration with non-existent JSONL file"""
    jsonl_path = tmp_path / "nonexistent.jsonl"
    db_path = tmp_path / "test.db"

    count = migrate_jsonl_to_sqlite(jsonl_path, db_path, backup=False)

    assert count == 0


def test_migrate_jsonl_to_sqlite_with_jobs(tmp_path):
    """Test migration with sample jobs"""
    # Create sample JSONL file
    jsonl_path = tmp_path / "jobs.jsonl"
    jobs = [
        {
            "job_id": "123",
            "title": "ML Engineer",
            "company": "Anthropic",
            "location": "SF",
            "scraped_at": "2026-02-15T10:00:00Z",
            "salary": "$150K",
            "raw_description": "Remote ML engineer",
        },
        {
            "job_id": "456",
            "title": "Data Scientist",
            "company": "OpenAI",
            "location": "NYC",
            "scraped_at": "2026-02-15T11:00:00Z",
            "salary": "$160K",
            "raw_description": "Onsite data scientist",
        }
    ]

    with open(jsonl_path, 'w') as f:
        for job in jobs:
            f.write(json.dumps(job) + '\n')

    db_path = tmp_path / "test.db"

    # Run migration
    count = migrate_jsonl_to_sqlite(jsonl_path, db_path, backup=True)

    assert count == 2

    # Verify backup created
    backup_path = tmp_path / "jobs.jsonl.backup"
    assert backup_path.exists()

    # Verify jobs in database
    db = JobDatabase(db_path)
    job1 = db.get_job("123")
    job2 = db.get_job("456")

    assert job1 is not None
    assert job1["title"] == "ML Engineer"
    assert job1["company"] == "Anthropic"
    assert job1["remote_eligible"] == 1  # SQLite stores boolean as INTEGER (1 = True)

    assert job2 is not None
    assert job2["title"] == "Data Scientist"
    assert job2["company"] == "OpenAI"

    db.close()


def test_migrate_jsonl_to_sqlite_malformed_json(tmp_path):
    """Test migration handles malformed JSON gracefully"""
    jsonl_path = tmp_path / "malformed.jsonl"

    with open(jsonl_path, 'w') as f:
        f.write('{"job_id": "123", "title": "Valid"}\n')
        f.write('invalid json line\n')
        f.write('{"job_id": "456", "title": "Also Valid"}\n')

    db_path = tmp_path / "test.db"

    # Should skip malformed line but migrate valid ones
    count = migrate_jsonl_to_sqlite(jsonl_path, db_path, backup=False)

    assert count == 2

    # Verify only valid jobs migrated
    db = JobDatabase(db_path)
    assert db.get_job("123") is not None
    assert db.get_job("456") is not None
    db.close()


def test_migrate_jsonl_to_sqlite_no_backup(tmp_path):
    """Test migration without backup"""
    jsonl_path = tmp_path / "jobs.jsonl"

    with open(jsonl_path, 'w') as f:
        f.write('{"job_id": "123", "title": "Test"}\n')

    db_path = tmp_path / "test.db"

    count = migrate_jsonl_to_sqlite(jsonl_path, db_path, backup=False)

    assert count == 1

    # Verify no backup created
    backup_path = tmp_path / "jobs.jsonl.backup"
    assert not backup_path.exists()
