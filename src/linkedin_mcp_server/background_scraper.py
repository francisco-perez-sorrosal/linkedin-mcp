"""Background scraper service for autonomous LinkedIn job monitoring"""

import asyncio
from dataclasses import asdict, dataclass
from datetime import datetime

from loguru import logger

from linkedin_mcp_server.db import JobDatabase
from linkedin_mcp_server.scraper import (
    create_client,
    fetch_job_details,
    search_jobs_pages,
)


@dataclass
class ScrapingProfile:
    """Configuration for a background scraping profile"""

    id: int
    name: str
    location: str
    keywords: str
    distance: int
    time_filter: str
    refresh_interval: int
    enabled: bool
    last_scraped_at: str | None
    created_at: str
    updated_at: str


class BackgroundScraperService:
    """Autonomous background scraper service with async workers"""

    def __init__(self, db: JobDatabase):
        self.db = db
        self.worker_tasks: dict[int, asyncio.Task] = {}  # profile_id → task
        self.shutdown_event = asyncio.Event()
        self.job_semaphore = asyncio.Semaphore(3)  # Conservative to avoid 429s
        self.company_semaphore = asyncio.Semaphore(
            2
        )  # Conservative for company enrichment

    async def start(self):
        """Load profiles from DB and spawn worker tasks"""
        logger.info("Starting background scraper service...")

        # Seed default profile if none exist
        profiles = self.db.list_profiles()
        if not profiles:
            self.db.seed_default_profile()
            profiles = self.db.list_profiles()

        # Spawn worker for each enabled profile
        for profile_dict in profiles:
            profile = ScrapingProfile(**profile_dict)
            if profile.enabled:
                await self._spawn_worker(profile)

        # Start profile reload loop (check for new/updated/deleted profiles every 30s)
        asyncio.create_task(self._reload_profiles_loop())

        logger.info(f"Started {len(self.worker_tasks)} scraping workers")

    async def stop(self):
        """Gracefully shutdown all workers"""
        logger.info("Stopping background scraper service...")
        self.shutdown_event.set()

        # Cancel all worker tasks
        for task in self.worker_tasks.values():
            task.cancel()

        # Wait for all tasks to complete (with timeout)
        await asyncio.gather(*self.worker_tasks.values(), return_exceptions=True)

        logger.info("Background scraper service stopped")

    async def _spawn_worker(self, profile: ScrapingProfile):
        """Spawn async worker task for a profile"""
        if profile.id in self.worker_tasks:
            logger.warning(f"Worker already exists for profile {profile.id}")
            return

        task = asyncio.create_task(self._run_profile_worker(profile))
        self.worker_tasks[profile.id] = task
        logger.info(f"Spawned worker for profile {profile.id}")

    async def _kill_worker(self, profile_id: int):
        """Cancel worker task for a profile"""
        if profile_id not in self.worker_tasks:
            return

        task = self.worker_tasks.pop(profile_id)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        logger.info(f"Killed worker for profile {profile_id}")

    async def _reload_profiles_loop(self):
        """Poll profiles table every 30s for changes"""
        while not self.shutdown_event.is_set():
            try:
                await asyncio.sleep(30)

                # Get current profiles from DB
                current_profiles = {p["id"]: p for p in self.db.list_profiles()}
                current_ids = set(current_profiles.keys())
                running_ids = set(self.worker_tasks.keys())

                # Spawn workers for new profiles
                for profile_id in current_ids - running_ids:
                    profile = ScrapingProfile(**current_profiles[profile_id])
                    if profile.enabled:
                        await self._spawn_worker(profile)

                # Kill workers for deleted/disabled profiles
                for profile_id in running_ids - current_ids:
                    await self._kill_worker(profile_id)

                # Check for disabled profiles
                for profile_id in current_ids & running_ids:
                    profile = ScrapingProfile(**current_profiles[profile_id])
                    if not profile.enabled:
                        await self._kill_worker(profile_id)

            except Exception as e:
                logger.error(f"Error reloading profiles: {e}")

    async def _run_profile_worker(self, profile: ScrapingProfile):
        """Worker loop for a single profile - scrape, wait, repeat"""
        logger.info(f"Worker started for profile {profile.id}")

        while not self.shutdown_event.is_set():
            try:
                # Scrape jobs for this profile
                count = await self._scrape_profile_once(profile)
                logger.info(f"Profile {profile.id}: scraped {count} jobs")

                # Update last_run timestamp
                self.db.update_profile_last_run(
                    profile.id, datetime.now().isoformat()
                )

                # Wait for refresh_interval before next scrape
                await asyncio.sleep(profile.refresh_interval)

            except asyncio.CancelledError:
                logger.info(f"Worker cancelled for profile {profile.id}")
                break
            except Exception as e:
                logger.error(f"Error in worker for profile {profile.id}: {e}")
                # Exponential backoff on error
                await asyncio.sleep(min(profile.refresh_interval, 300))

    async def _scrape_profile_once(self, profile: ScrapingProfile) -> int:
        """Execute one scrape cycle for a profile

        Args:
            profile: ScrapingProfile configuration

        Returns:
            Count of new/updated jobs
        """
        try:
            # Build filters
            filters = {"f_TPR": profile.time_filter}  # Time filter: r7200 (2h) default

            # Fetch search results (1 page = 10 jobs)
            async with create_client() as client:
                summaries = await search_jobs_pages(
                    client,
                    query=profile.keywords,
                    location=profile.location,
                    distance=profile.distance,
                    num_pages=5,  # 50 jobs per scrape
                    filters=filters,
                )

            if not summaries:
                logger.info(f"No jobs found for profile {profile.id}")
                return 0

            # Fetch job details with concurrency control
            job_ids = [s.job_id for s in summaries if s.job_id != "N/A"]

            async with create_client() as client:
                details = await fetch_job_details(client, job_ids, self.job_semaphore)

            # Convert JobDetail to dict, skip failed scrapes to avoid overwriting good data
            jobs_to_upsert = []
            skipped = 0
            for detail in details:
                if detail.title == "N/A" or detail.company == "N/A":
                    skipped += 1
                    logger.warning(f"Skipping job {detail.job_id}: detail fetch returned N/A fields")
                    continue

                job_dict = asdict(detail)
                job_dict["profile_id"] = profile.id

                # Detect changes (compare with existing DB record)
                existing = self.db.get_job(detail.job_id)
                if existing:
                    await self._detect_job_changes(existing, job_dict)

                jobs_to_upsert.append(job_dict)

            if skipped:
                logger.warning(f"Profile {profile.id}: skipped {skipped}/{len(details)} jobs with N/A fields")

            # Batch upsert to DB
            count = self.db.upsert_jobs(jobs_to_upsert)

            return count

        except Exception as e:
            logger.error(f"Error scraping profile {profile.id}: {e}")
            raise

    async def _detect_job_changes(self, old_job: dict, new_job: dict):
        """Compare old and new job records, record changes to job_changes table

        Args:
            old_job: Existing job record from database
            new_job: New job data from scraping
        """
        fields_to_track = ["salary", "number_of_applicants", "raw_description"]

        for field in fields_to_track:
            old_value = old_job.get(field, "")
            new_value = new_job.get(field, "")

            if old_value != new_value:
                self.db.record_job_change(
                    job_id=old_job["job_id"],
                    field_name=field,
                    old_value=str(old_value),
                    new_value=str(new_value),
                )
