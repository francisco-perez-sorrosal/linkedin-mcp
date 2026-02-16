"""
SQLite database layer for LinkedIn job cache.

Provides persistent storage with:
- Job metadata with full-text search (FTS5)
- Scraping profile configurations
- Application tracking
- Company enrichment data
- Job change detection audit log
"""

import sqlite3
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any
from loguru import logger


def normalize_company_name(name: str) -> str:
    """
    Normalize company name for fuzzy matching.

    Strips common suffixes (Inc, LLC, Ltd, Corp) and normalizes case.
    """
    normalized = name.strip().lower()

    # Remove common company suffixes
    suffixes = [
        ", inc.", " inc.", " inc",
        ", llc", " llc",
        ", ltd.", " ltd.", " ltd",
        ", corp.", " corp.", " corp",
        ", corporation", " corporation",
        " limited",
        ", co.", " co.",
    ]

    for suffix in suffixes:
        if normalized.endswith(suffix):
            normalized = normalized[:-len(suffix)]
            break

    return normalized.strip()


class JobDatabase:
    """
    SQLite database for job caching and metadata storage.

    Features:
    - WAL mode for concurrent reads during background scraping
    - FTS5 full-text search on job descriptions
    - Structured querying with composable filters
    - Application tracking and company enrichment
    - Job change detection audit log
    """

    def __init__(self, db_path: Path | str):
        """
        Initialize database connection.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Connect with WAL mode for concurrent reads
        self.conn = sqlite3.connect(
            str(self.db_path),
            check_same_thread=False,  # Allow multi-threaded access
            timeout=30.0,  # Wait up to 30s for locks
        )
        self.conn.row_factory = sqlite3.Row  # Return dicts instead of tuples

        # Enable WAL mode for better concurrency
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")  # Faster writes, still safe in WAL
        self.conn.execute("PRAGMA foreign_keys=ON")  # Enforce FK constraints

        logger.info(f"Database initialized at {self.db_path}")

    def initialize_schema(self) -> None:
        """
        Create all tables, indexes, and FTS5 virtual table.

        Idempotent - safe to call multiple times.
        """
        cursor = self.conn.cursor()

        # 1. Jobs table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                company TEXT NOT NULL,
                normalized_company_name TEXT NOT NULL,
                location TEXT NOT NULL,
                posted_date TEXT NOT NULL,
                posted_date_iso TEXT NOT NULL,
                scraped_at TEXT NOT NULL,
                last_seen TEXT NOT NULL,

                -- Structured salary
                salary_min REAL,
                salary_max REAL,
                salary_currency TEXT,
                equity_offered INTEGER DEFAULT 0,

                -- Decision-making fields
                remote_eligible INTEGER DEFAULT 0,
                visa_sponsorship INTEGER DEFAULT 0,
                skills TEXT,
                easy_apply INTEGER DEFAULT 0,
                number_of_applicants TEXT,

                -- Description insights (for composable responses)
                description_summary TEXT,
                key_requirements TEXT,  -- JSON array
                key_responsibilities_preview TEXT,

                -- Full description and metadata
                raw_description TEXT,
                employment_type TEXT,
                seniority_level TEXT,
                job_function TEXT,
                industries TEXT,
                benefits_badge TEXT,

                -- References
                company_url TEXT,
                url TEXT,
                profile_id INTEGER,
                source TEXT DEFAULT 'linkedin_guest_api',

                FOREIGN KEY (profile_id) REFERENCES profiles(id) ON DELETE SET NULL
            )
        """)

        # 2. Profiles table (scraping configurations)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                location TEXT NOT NULL,
                keywords TEXT NOT NULL,
                distance INTEGER DEFAULT 25,
                time_filter TEXT DEFAULT 'r7200',
                refresh_interval INTEGER DEFAULT 3600,
                enabled INTEGER DEFAULT 1,
                last_scraped_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)

        # 3. Applications table (job application tracking)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS applications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL,
                applied_at TEXT NOT NULL,
                status TEXT NOT NULL,
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,

                FOREIGN KEY (job_id) REFERENCES jobs(job_id) ON DELETE CASCADE,
                UNIQUE(job_id)
            )
        """)

        # 4. Company enrichment table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS company_enrichment (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_name TEXT NOT NULL UNIQUE,
                normalized_company_name TEXT NOT NULL,
                company_size TEXT,
                company_industry TEXT,
                company_description TEXT,
                company_website TEXT,
                company_headquarters TEXT,
                company_founded INTEGER,
                company_specialties TEXT,  -- JSON array
                company_linkedin_url TEXT,
                scraped_at TEXT NOT NULL,
                next_refresh_at TEXT NOT NULL,

                UNIQUE(normalized_company_name)
            )
        """)

        # 5. Job changes table (audit log)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS job_changes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL,
                changed_at TEXT NOT NULL,
                field_name TEXT NOT NULL,
                old_value TEXT,
                new_value TEXT,

                FOREIGN KEY (job_id) REFERENCES jobs(job_id) ON DELETE CASCADE
            )
        """)

        # 6. FTS5 virtual table for full-text search
        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS jobs_fts USING fts5(
                job_id UNINDEXED,
                title,
                company,
                raw_description,
                skills,
                content=jobs,
                content_rowid=rowid
            )
        """)

        # 7. FTS5 triggers to keep in sync with jobs table
        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS jobs_fts_insert AFTER INSERT ON jobs BEGIN
                INSERT INTO jobs_fts(job_id, title, company, raw_description, skills)
                VALUES (new.job_id, new.title, new.company, new.raw_description, new.skills);
            END
        """)

        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS jobs_fts_update AFTER UPDATE ON jobs BEGIN
                DELETE FROM jobs_fts WHERE job_id = old.job_id;
                INSERT INTO jobs_fts(job_id, title, company, raw_description, skills)
                VALUES (new.job_id, new.title, new.company, new.raw_description, new.skills);
            END
        """)

        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS jobs_fts_delete AFTER DELETE ON jobs BEGIN
                DELETE FROM jobs_fts WHERE job_id = old.job_id;
            END
        """)

        # 8. Indexes for query performance
        # Jobs table indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_company ON jobs(normalized_company_name)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_location ON jobs(location)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_posted_date ON jobs(posted_date_iso DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_scraped_at ON jobs(scraped_at DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_remote ON jobs(remote_eligible) WHERE remote_eligible = 1")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_visa ON jobs(visa_sponsorship) WHERE visa_sponsorship = 1")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_profile ON jobs(profile_id)")

        # Applications table indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_applications_job_id ON applications(job_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_applications_status ON applications(status)")

        # Company enrichment indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_company_normalized ON company_enrichment(normalized_company_name)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_company_refresh ON company_enrichment(next_refresh_at)")

        self.conn.commit()
        logger.info("Database schema initialized successfully")

    def close(self) -> None:
        """Close database connection."""
        if self.conn:
            self.conn.close()
            logger.info("Database connection closed")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()

    # ========== Job CRUD Operations ==========

    def upsert_jobs(self, jobs: list[dict]) -> int:
        """
        Insert or update jobs in batch.

        Uses INSERT OR REPLACE for upsert behavior. Automatically normalizes
        company names and sets last_seen timestamp.

        Args:
            jobs: List of job dictionaries with all required fields

        Returns:
            Number of jobs inserted/updated
        """
        if not jobs:
            return 0

        cursor = self.conn.cursor()

        # Prepare jobs with normalized company names
        for job in jobs:
            if "normalized_company_name" not in job:
                job["normalized_company_name"] = normalize_company_name(job["company"])

            # Set last_seen to current time if not present
            if "last_seen" not in job:
                job["last_seen"] = datetime.now(timezone.utc).isoformat()

        # Build INSERT OR REPLACE statement
        columns = [
            "job_id", "title", "company", "normalized_company_name", "location",
            "posted_date", "posted_date_iso", "scraped_at", "last_seen",
            "salary_min", "salary_max", "salary_currency", "equity_offered",
            "remote_eligible", "visa_sponsorship", "skills", "easy_apply",
            "number_of_applicants", "description_summary", "key_requirements",
            "key_responsibilities_preview", "raw_description", "employment_type",
            "seniority_level", "job_function", "industries", "benefits_badge",
            "company_url", "url", "profile_id", "source"
        ]

        placeholders = ", ".join(["?" for _ in columns])
        sql = f"INSERT OR REPLACE INTO jobs ({', '.join(columns)}) VALUES ({placeholders})"

        # Extract values for each job
        rows = []
        for job in jobs:
            row = [job.get(col) for col in columns]
            rows.append(row)

        cursor.executemany(sql, rows)
        self.conn.commit()

        count = cursor.rowcount
        logger.info(f"Upserted {count} jobs")
        return count

    def get_job(self, job_id: str) -> dict | None:
        """
        Retrieve a single job by ID.

        Args:
            job_id: Job ID to retrieve

        Returns:
            Job dictionary or None if not found
        """
        cursor = self.conn.execute(
            "SELECT * FROM jobs WHERE job_id = ?",
            (job_id,)
        )
        row = cursor.fetchone()

        if row:
            return dict(row)
        return None

    def query_jobs(
        self,
        company: str | None = None,
        location: str | None = None,
        keywords: str | None = None,
        posted_after_hours: int | None = None,
        remote_only: bool = False,
        visa_sponsorship: bool = False,
        application_status: str | None = None,
        limit: int = 20,
        offset: int = 0,
        sort_by: str = "posted_date",
    ) -> list[dict]:
        """
        Query jobs with composable filters.

        Args:
            company: Filter by company name (case-insensitive, fuzzy)
            location: Filter by location (case-insensitive, partial match)
            keywords: Full-text search keywords (FTS5)
            posted_after_hours: Only jobs posted within N hours
            remote_only: Only remote-eligible jobs
            visa_sponsorship: Only jobs offering visa sponsorship
            application_status: Filter by application status ("not_applied", "applied", etc.)
            limit: Maximum number of results
            offset: Pagination offset
            sort_by: Sort field ("posted_date", "scraped_at", "applicants")

        Returns:
            List of job dictionaries matching filters
        """
        where_clauses = []
        params = []

        # Base query with LEFT JOIN for applications and company enrichment
        base_query = """
            SELECT
                j.*,
                a.status as application_status,
                a.applied_at,
                c.company_size,
                c.company_industry
            FROM jobs j
            LEFT JOIN applications a ON j.job_id = a.job_id
            LEFT JOIN company_enrichment c ON j.normalized_company_name = c.normalized_company_name
        """

        # Build WHERE clause
        if company:
            normalized = normalize_company_name(company)
            where_clauses.append("j.normalized_company_name LIKE ?")
            params.append(f"%{normalized}%")

        if location:
            where_clauses.append("LOWER(j.location) LIKE LOWER(?)")
            params.append(f"%{location}%")

        if keywords:
            # FTS5 search - must join with jobs_fts
            where_clauses.append("j.job_id IN (SELECT job_id FROM jobs_fts WHERE jobs_fts MATCH ?)")
            params.append(keywords)

        if posted_after_hours:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=posted_after_hours)
            where_clauses.append("j.posted_date_iso >= ?")
            params.append(cutoff.isoformat())

        if remote_only:
            where_clauses.append("j.remote_eligible = 1")

        if visa_sponsorship:
            where_clauses.append("j.visa_sponsorship = 1")

        if application_status:
            if application_status == "not_applied":
                where_clauses.append("a.job_id IS NULL")
            else:
                where_clauses.append("a.status = ?")
                params.append(application_status)

        # Combine WHERE clauses
        if where_clauses:
            base_query += " WHERE " + " AND ".join(where_clauses)

        # Add ORDER BY
        order_map = {
            "posted_date": "j.posted_date_iso DESC",
            "scraped_at": "j.scraped_at DESC",
            "applicants": "CAST(j.number_of_applicants AS INTEGER) DESC",
        }
        order_clause = order_map.get(sort_by, "j.posted_date_iso DESC")
        base_query += f" ORDER BY {order_clause}"

        # Add pagination
        base_query += " LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        # Execute query
        cursor = self.conn.execute(base_query, params)
        rows = cursor.fetchall()

        # Convert to list of dicts
        return [dict(row) for row in rows]

    def count_jobs(
        self,
        company: str | None = None,
        location: str | None = None,
        keywords: str | None = None,
        posted_after_hours: int | None = None,
        remote_only: bool = False,
        visa_sponsorship: bool = False,
        application_status: str | None = None,
    ) -> int:
        """
        Count jobs matching filters (for pagination).

        Args:
            Same as query_jobs() but without limit/offset/sort_by

        Returns:
            Total count of matching jobs
        """
        where_clauses = []
        params = []

        # Base query
        base_query = """
            SELECT COUNT(DISTINCT j.job_id)
            FROM jobs j
            LEFT JOIN applications a ON j.job_id = a.job_id
        """

        # Build WHERE clause (same logic as query_jobs)
        if company:
            normalized = normalize_company_name(company)
            where_clauses.append("j.normalized_company_name LIKE ?")
            params.append(f"%{normalized}%")

        if location:
            where_clauses.append("LOWER(j.location) LIKE LOWER(?)")
            params.append(f"%{location}%")

        if keywords:
            where_clauses.append("j.job_id IN (SELECT job_id FROM jobs_fts WHERE jobs_fts MATCH ?)")
            params.append(keywords)

        if posted_after_hours:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=posted_after_hours)
            where_clauses.append("j.posted_date_iso >= ?")
            params.append(cutoff.isoformat())

        if remote_only:
            where_clauses.append("j.remote_eligible = 1")

        if visa_sponsorship:
            where_clauses.append("j.visa_sponsorship = 1")

        if application_status:
            if application_status == "not_applied":
                where_clauses.append("a.job_id IS NULL")
            else:
                where_clauses.append("a.status = ?")
                params.append(application_status)

        # Combine WHERE clauses
        if where_clauses:
            base_query += " WHERE " + " AND ".join(where_clauses)

        cursor = self.conn.execute(base_query, params)
        return cursor.fetchone()[0]

    def delete_old_jobs(self, max_age_seconds: int) -> int:
        """
        Delete jobs older than max_age_seconds.

        Args:
            max_age_seconds: Maximum age in seconds (based on scraped_at)

        Returns:
            Number of jobs deleted
        """
        from datetime import timedelta

        cutoff = datetime.now(timezone.utc) - timedelta(seconds=max_age_seconds)

        cursor = self.conn.execute(
            "DELETE FROM jobs WHERE scraped_at < ?",
            (cutoff.isoformat(),)
        )
        self.conn.commit()

        count = cursor.rowcount
        logger.info(f"Deleted {count} old jobs (older than {max_age_seconds}s)")
        return count

    # ========== Profile CRUD Operations ==========

    def upsert_profile(self, profile: dict) -> int:
        """
        Insert or update a scraping profile.

        Args:
            profile: Profile dictionary with name, location, keywords, etc.

        Returns:
            Profile ID (auto-generated for new profiles)
        """
        now = datetime.now(timezone.utc).isoformat()

        # Check if profile exists by name
        cursor = self.conn.execute(
            "SELECT id FROM profiles WHERE name = ?",
            (profile["name"],)
        )
        row = cursor.fetchone()

        if row:
            # Update existing profile
            profile_id = row[0]
            self.conn.execute(
                """
                UPDATE profiles SET
                    location = ?, keywords = ?, distance = ?,
                    time_filter = ?, refresh_interval = ?, enabled = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    profile["location"],
                    profile["keywords"],
                    profile.get("distance", 25),
                    profile.get("time_filter", "r7200"),
                    profile.get("refresh_interval", 3600),
                    profile.get("enabled", 1),
                    now,
                    profile_id,
                )
            )
            self.conn.commit()
            logger.info(f"Updated profile {profile_id}: {profile['name']}")
        else:
            # Insert new profile
            cursor = self.conn.execute(
                """
                INSERT INTO profiles (
                    name, location, keywords, distance, time_filter,
                    refresh_interval, enabled, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    profile["name"],
                    profile["location"],
                    profile["keywords"],
                    profile.get("distance", 25),
                    profile.get("time_filter", "r7200"),
                    profile.get("refresh_interval", 3600),
                    profile.get("enabled", 1),
                    now,
                    now,
                )
            )
            self.conn.commit()
            profile_id = cursor.lastrowid
            logger.info(f"Created profile {profile_id}: {profile['name']}")

        return profile_id

    def get_profile(self, profile_id: int) -> dict | None:
        """
        Retrieve a single profile by ID.

        Args:
            profile_id: Profile ID

        Returns:
            Profile dictionary or None if not found
        """
        cursor = self.conn.execute(
            "SELECT * FROM profiles WHERE id = ?",
            (profile_id,)
        )
        row = cursor.fetchone()

        if row:
            return dict(row)
        return None

    def list_profiles(self, enabled_only: bool = True) -> list[dict]:
        """
        List all profiles.

        Args:
            enabled_only: If True, only return enabled profiles

        Returns:
            List of profile dictionaries
        """
        if enabled_only:
            cursor = self.conn.execute(
                "SELECT * FROM profiles WHERE enabled = 1 ORDER BY created_at"
            )
        else:
            cursor = self.conn.execute(
                "SELECT * FROM profiles ORDER BY created_at"
            )

        return [dict(row) for row in cursor.fetchall()]

    def delete_profile(self, profile_id: int, hard_delete: bool = False):
        """
        Delete a profile (soft delete by default, set enabled=0).

        Args:
            profile_id: Profile ID to delete
            hard_delete: If True, permanently delete from database
        """
        if hard_delete:
            self.conn.execute("DELETE FROM profiles WHERE id = ?", (profile_id,))
            logger.info(f"Hard deleted profile {profile_id}")
        else:
            self.conn.execute(
                "UPDATE profiles SET enabled = 0, updated_at = ? WHERE id = ?",
                (datetime.now(timezone.utc).isoformat(), profile_id)
            )
            logger.info(f"Soft deleted profile {profile_id}")

        self.conn.commit()

    def update_profile_last_run(self, profile_id: int, timestamp: str):
        """
        Update the last_scraped_at timestamp for a profile.

        Args:
            profile_id: Profile ID
            timestamp: ISO timestamp of last scrape
        """
        self.conn.execute(
            "UPDATE profiles SET last_scraped_at = ?, updated_at = ? WHERE id = ?",
            (timestamp, datetime.now(timezone.utc).isoformat(), profile_id)
        )
        self.conn.commit()
        logger.info(f"Updated last_scraped_at for profile {profile_id}")

    def seed_default_profile(self) -> int | None:
        """
        Create default profile if no profiles exist.

        Default profile:
        - name: "default"
        - location: "San Francisco, CA"
        - keywords: "AI Engineer OR ML Engineer OR Research Engineer"
        - distance: 25
        - time_filter: "r7200" (2 hours)
        - refresh_interval: 7200 (2 hours)

        Returns:
            Profile ID if created, None if profiles already exist
        """
        # Check if any profiles exist
        cursor = self.conn.execute("SELECT COUNT(*) FROM profiles")
        count = cursor.fetchone()[0]

        if count > 0:
            logger.info("Profiles already exist, skipping default profile seeding")
            return None

        # Create default profile
        default_profile = {
            "name": "default",
            "location": "San Francisco, CA",
            "keywords": "AI Engineer OR ML Engineer OR Research Engineer",
            "distance": 25,
            "time_filter": "r7200",
            "refresh_interval": 7200,
            "enabled": 1,
        }

        profile_id = self.upsert_profile(default_profile)
        logger.info(f"Seeded default profile {profile_id}")
        return profile_id

    # ========== Application CRUD Operations ==========

    def mark_job_applied(self, job_id: str, notes: str = "") -> bool:
        """
        Mark a job as applied.

        Args:
            job_id: Job ID
            notes: Optional application notes

        Returns:
            True if successful, False if job not found
        """
        # Verify job exists
        job = self.get_job(job_id)
        if not job:
            logger.warning(f"Cannot mark job {job_id} as applied: job not found")
            return False

        now = datetime.now(timezone.utc).isoformat()

        # Insert or update application
        self.conn.execute(
            """
            INSERT INTO applications (job_id, applied_at, status, notes, created_at, updated_at)
            VALUES (?, ?, 'applied', ?, ?, ?)
            ON CONFLICT(job_id) DO UPDATE SET
                applied_at = excluded.applied_at,
                status = 'applied',
                notes = excluded.notes,
                updated_at = excluded.updated_at
            """,
            (job_id, now, notes, now, now)
        )
        self.conn.commit()
        logger.info(f"Marked job {job_id} as applied")
        return True

    def update_application_status(self, job_id: str, status: str, notes: str = "") -> bool:
        """
        Update application status.

        Args:
            job_id: Job ID
            status: New status (applied, interviewing, rejected, offered, accepted)
            notes: Optional notes

        Returns:
            True if successful, False if application not found
        """
        # Check if application exists
        cursor = self.conn.execute(
            "SELECT id FROM applications WHERE job_id = ?",
            (job_id,)
        )
        if not cursor.fetchone():
            logger.warning(f"Cannot update application for job {job_id}: not found")
            return False

        now = datetime.now(timezone.utc).isoformat()

        self.conn.execute(
            """
            UPDATE applications
            SET status = ?, notes = ?, updated_at = ?
            WHERE job_id = ?
            """,
            (status, notes, now, job_id)
        )
        self.conn.commit()
        logger.info(f"Updated application for job {job_id} to status '{status}'")
        return True

    def list_applications(self, status: str | None = None) -> list[dict]:
        """
        List applications, optionally filtered by status.

        Args:
            status: Filter by status (applied, interviewing, etc.)

        Returns:
            List of application dictionaries with job details
        """
        if status:
            cursor = self.conn.execute(
                """
                SELECT a.*, j.title, j.company, j.location
                FROM applications a
                JOIN jobs j ON a.job_id = j.job_id
                WHERE a.status = ?
                ORDER BY a.applied_at DESC
                """,
                (status,)
            )
        else:
            cursor = self.conn.execute(
                """
                SELECT a.*, j.title, j.company, j.location
                FROM applications a
                JOIN jobs j ON a.job_id = j.job_id
                ORDER BY a.applied_at DESC
                """
            )

        return [dict(row) for row in cursor.fetchall()]

    # ========== Company Enrichment CRUD Operations ==========

    def upsert_company_enrichment(self, company_data: dict):
        """
        Insert or update company enrichment data.

        Args:
            company_data: Company metadata dictionary
        """
        now = datetime.now(timezone.utc).isoformat()

        # Calculate next refresh (30 days from now)
        next_refresh = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()

        # Normalize company name
        normalized_name = normalize_company_name(company_data["company_name"])

        # Serialize company_specialties to JSON if it's a list
        specialties = company_data.get("company_specialties")
        if isinstance(specialties, list):
            specialties = json.dumps(specialties)

        self.conn.execute(
            """
            INSERT INTO company_enrichment (
                company_name, normalized_company_name, company_size, company_industry,
                company_description, company_website, company_headquarters,
                company_founded, company_specialties, company_linkedin_url,
                scraped_at, next_refresh_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(normalized_company_name) DO UPDATE SET
                company_name = excluded.company_name,
                company_size = excluded.company_size,
                company_industry = excluded.company_industry,
                company_description = excluded.company_description,
                company_website = excluded.company_website,
                company_headquarters = excluded.company_headquarters,
                company_founded = excluded.company_founded,
                company_specialties = excluded.company_specialties,
                company_linkedin_url = excluded.company_linkedin_url,
                scraped_at = excluded.scraped_at,
                next_refresh_at = excluded.next_refresh_at
            """,
            (
                company_data["company_name"],
                normalized_name,
                company_data.get("company_size"),
                company_data.get("company_industry"),
                company_data.get("company_description"),
                company_data.get("company_website"),
                company_data.get("company_headquarters"),
                company_data.get("company_founded"),
                specialties,
                company_data.get("company_linkedin_url"),
                now,
                next_refresh,
            )
        )
        self.conn.commit()
        logger.info(f"Upserted company enrichment for {company_data['company_name']}")

    def get_company_enrichment(self, company_name: str) -> dict | None:
        """
        Retrieve cached company enrichment data.

        Args:
            company_name: Company name (will be normalized for lookup)

        Returns:
            Company data dictionary or None if not found
        """
        normalized = normalize_company_name(company_name)

        cursor = self.conn.execute(
            "SELECT * FROM company_enrichment WHERE normalized_company_name = ?",
            (normalized,)
        )
        row = cursor.fetchone()

        if row:
            result = dict(row)
            # Deserialize company_specialties from JSON
            if result.get("company_specialties"):
                try:
                    result["company_specialties"] = json.loads(result["company_specialties"])
                except json.JSONDecodeError:
                    pass
            return result
        return None

    def get_companies_needing_refresh(self) -> list[str]:
        """
        Get list of company names that need refreshing.

        Returns:
            List of company names where next_refresh_at < now()
        """
        now = datetime.now(timezone.utc).isoformat()

        cursor = self.conn.execute(
            "SELECT company_name FROM company_enrichment WHERE next_refresh_at < ?",
            (now,)
        )

        return [row[0] for row in cursor.fetchall()]

    # ========== Job Changes CRUD Operations ==========

    def record_job_change(self, job_id: str, field_name: str, old_value: str | None, new_value: str | None):
        """
        Record a change to a job field.

        Args:
            job_id: Job ID
            field_name: Name of changed field
            old_value: Previous value
            new_value: New value
        """
        now = datetime.now(timezone.utc).isoformat()

        self.conn.execute(
            """
            INSERT INTO job_changes (job_id, changed_at, field_name, old_value, new_value)
            VALUES (?, ?, ?, ?, ?)
            """,
            (job_id, now, field_name, old_value, new_value)
        )
        self.conn.commit()
        logger.info(f"Recorded change for job {job_id}: {field_name} changed")

    def get_job_changes(self, since_hours: int = 24) -> list[dict]:
        """
        Get recent job changes.

        Args:
            since_hours: How many hours back to query

        Returns:
            List of job change records
        """
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=since_hours)).isoformat()

        cursor = self.conn.execute(
            """
            SELECT jc.*, j.title, j.company
            FROM job_changes jc
            JOIN jobs j ON jc.job_id = j.job_id
            WHERE jc.changed_at >= ?
            ORDER BY jc.changed_at DESC
            """,
            (cutoff,)
        )

        return [dict(row) for row in cursor.fetchall()]

    # ========== Analytics Queries ==========

    def get_cache_analytics(self) -> dict:
        """
        Get comprehensive analytics across all tables.

        Returns:
            Dictionary with analytics for jobs, profiles, applications,
            company enrichment, and cache health
        """
        now = datetime.now(timezone.utc)

        # ===== Job Analytics =====

        # Total jobs
        cursor = self.conn.execute("SELECT COUNT(*) FROM jobs")
        total_jobs = cursor.fetchone()[0]

        # Jobs by age buckets
        day_1_cutoff = (now - timedelta(hours=24)).isoformat()
        day_7_cutoff = (now - timedelta(days=7)).isoformat()
        day_30_cutoff = (now - timedelta(days=30)).isoformat()

        cursor = self.conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE scraped_at >= ?", (day_1_cutoff,)
        )
        fresh_24h = cursor.fetchone()[0]

        cursor = self.conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE scraped_at >= ?", (day_7_cutoff,)
        )
        recent_7d = cursor.fetchone()[0]

        cursor = self.conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE scraped_at >= ?", (day_30_cutoff,)
        )
        old_30d = cursor.fetchone()[0]

        stale = total_jobs - old_30d

        # Jobs by application status
        status_counts = {
            "not_applied": 0,
            "applied": 0,
            "interviewing": 0,
            "rejected": 0,
            "offered": 0,
            "accepted": 0,
        }

        # Count not_applied (LEFT JOIN where application is NULL)
        cursor = self.conn.execute(
            """
            SELECT COUNT(*)
            FROM jobs j
            LEFT JOIN applications a ON j.job_id = a.job_id
            WHERE a.job_id IS NULL
            """
        )
        status_counts["not_applied"] = cursor.fetchone()[0]

        # Count by application status
        cursor = self.conn.execute(
            """
            SELECT status, COUNT(*) as count
            FROM applications
            GROUP BY status
            """
        )
        for row in cursor.fetchall():
            status = row[0]
            count = row[1]
            if status in status_counts:
                status_counts[status] = count

        # Top 10 companies by job count
        cursor = self.conn.execute(
            """
            SELECT company, normalized_company_name, COUNT(*) as count
            FROM jobs
            GROUP BY normalized_company_name
            ORDER BY count DESC
            LIMIT 10
            """
        )
        top_companies = [
            {"company": row[0], "normalized_name": row[1], "count": row[2]}
            for row in cursor.fetchall()
        ]

        # Top 10 locations by job count
        cursor = self.conn.execute(
            """
            SELECT location, COUNT(*) as count
            FROM jobs
            GROUP BY location
            ORDER BY count DESC
            LIMIT 10
            """
        )
        top_locations = [
            {"location": row[0], "count": row[1]}
            for row in cursor.fetchall()
        ]

        # ===== Scraping Profiles Analytics =====

        profiles = []
        cursor = self.conn.execute("SELECT * FROM profiles")
        for profile_row in cursor.fetchall():
            profile = dict(profile_row)

            # Count jobs for this profile
            job_count_cursor = self.conn.execute(
                "SELECT COUNT(*) FROM jobs WHERE profile_id = ?",
                (profile["id"],)
            )
            total_jobs_cached = job_count_cursor.fetchone()[0]

            # Compute next_scrape_at
            next_scrape_at = None
            if profile["last_scraped_at"]:
                last_scraped = datetime.fromisoformat(profile["last_scraped_at"])
                next_scrape = last_scraped + timedelta(seconds=profile["refresh_interval"])
                next_scrape_at = next_scrape.isoformat()

            profiles.append({
                "profile_id": profile["id"],
                "name": profile["name"],
                "location": profile["location"],
                "distance": profile["distance"],
                "query": profile["keywords"],
                "refresh_interval_hours": profile["refresh_interval"] / 3600,
                "time_filter": profile["time_filter"],
                "enabled": bool(profile["enabled"]),
                "last_scraped_at": profile["last_scraped_at"],
                "next_scrape_at": next_scrape_at,
                "total_jobs_cached": total_jobs_cached,
                "error_count_24h": 0,  # Not implemented (requires error logging)
            })

        # ===== Applications Analytics =====

        cursor = self.conn.execute("SELECT COUNT(*) FROM applications")
        total_applications = cursor.fetchone()[0]

        app_status_counts = {
            "applied": 0,
            "interviewing": 0,
            "rejected": 0,
            "offered": 0,
            "accepted": 0,
        }

        cursor = self.conn.execute(
            """
            SELECT status, COUNT(*) as count
            FROM applications
            GROUP BY status
            """
        )
        for row in cursor.fetchall():
            status = row[0]
            count = row[1]
            if status in app_status_counts:
                app_status_counts[status] = count

        # ===== Company Enrichment Analytics =====

        cursor = self.conn.execute("SELECT COUNT(*) FROM company_enrichment")
        total_companies = cursor.fetchone()[0]

        cursor = self.conn.execute(
            "SELECT COUNT(*) FROM company_enrichment WHERE next_refresh_at < ?",
            (now.isoformat(),)
        )
        companies_needing_refresh = cursor.fetchone()[0]

        # ===== Cache Health =====

        # Database file size
        size_mb = 0.0
        if self.db_path.exists():
            size_bytes = self.db_path.stat().st_size
            size_mb = size_bytes / (1024 * 1024)

        # Oldest and newest job
        oldest_job = None
        newest_job = None

        cursor = self.conn.execute(
            "SELECT MIN(scraped_at), MAX(scraped_at) FROM jobs"
        )
        row = cursor.fetchone()
        if row[0]:
            oldest_job = row[0]
            newest_job = row[1]

        # ===== Assemble analytics =====

        return {
            "jobs": {
                "total": total_jobs,
                "by_age": {
                    "fresh_24h": fresh_24h,
                    "recent_7d": recent_7d,
                    "old_30d": old_30d,
                    "stale": stale,
                },
                "by_application_status": status_counts,
                "top_companies": top_companies,
                "top_locations": top_locations,
            },
            "scraping_profiles": profiles,
            "applications": {
                "total": total_applications,
                **app_status_counts,
            },
            "company_enrichment": {
                "total": total_companies,
                "needing_refresh": companies_needing_refresh,
            },
            "cache_health": {
                "size_mb": round(size_mb, 2),
                "oldest_job": oldest_job,
                "newest_job": newest_job,
            },
        }
