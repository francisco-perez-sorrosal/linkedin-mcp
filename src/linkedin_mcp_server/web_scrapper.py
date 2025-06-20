import asyncio
import os
import random
import time
from dataclasses import dataclass
from datetime import datetime
from functools import partial
from multiprocessing import Pool, cpu_count
from typing import Any, Dict, List, Set, Tuple

import bs4
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from loguru import logger
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from linkedin_mcp_server.cache import BasicInMemoryCache


# Load environment variables from .env file
env_loaded: bool = load_dotenv()

if not env_loaded:
    raise Exception("Failed to load environment variables from .env file")


def setup_webdriver() -> WebDriver:
    """
    Setup Chrome webdriver with headless mode and common options
    
    Returns:
        Configured Chrome webdriver
    """
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    
    try:
        return webdriver.Chrome(options=chrome_options)
    except Exception as e:
        logger.error(f"Failed to initialize webdriver: {e}")
        raise


def extract_job_description_worker(job_id: str) -> Dict[str, Any]:
    """
    Worker function for extracting job description in a separate process.
    
    Args:
        job_id: LinkedIn job ID to process
        
    Returns:
        Dict containing job details
    """
    # Each worker needs its own WebDriver instance
    driver = setup_webdriver()
    try:
        url = JOB_URL.format(job_id=job_id)
        logger.info(f"Worker processing job ID {job_id}")
        
        # Initialize job details with default values and URL
        job_details = {
            "linkedin_job_id": job_id,  # Using a fixed key name instead of class attribute
            "url": url,
            "source": "linkedin",
            "scraped_at": datetime.now().isoformat(),
            "title": "N/A",
            "location": "N/A",
            "company": "N/A",
            "posted_date": "N/A",
            "number_of_applicants": "N/A",
            "raw_description": "N/A",
            "employment_type": "N/A",
            "seniority_level": "N/A",
            "job_function": "N/A",
            "industries": "N/A",
            "skills": "N/A",
            "company_details": "N/A"
        }
        
        driver.get(url)
        
        # Extract job title
        try:
            title_elem = driver.find_element(
                By.CSS_SELECTOR,
                ".top-card-layout__title, .topcard__title"
            )
            job_details["title"] = title_elem.text.strip()
            logger.info(f"Extracted job title: {job_details['title']}")
        except Exception as e:
            logger.error(f"Failed to extract job title: {e}")
        
        # Extract company name and URL
        try:
            company_elem = driver.find_element(
                By.CSS_SELECTOR,
                "a.topcard__org-name-link, .topcard__flavor--black-link"
            )
            job_details["company"] = company_elem.text.strip()
            company_url = company_elem.get_attribute('href')
            if company_url:
                job_details["company_url"] = company_url.split('?')[0]  # Remove tracking params
            logger.info(f"Extracted company: {job_details['company']}")
        except Exception as e:
            logger.error(f"Failed to extract company name: {e}")
        
        # Extract location
        try:
            location_elem = driver.find_element(
                By.CSS_SELECTOR,
                ".topcard__flavor--bullet, .topcard__flavor:not(.topcard__flavor--black-link)"
            )
            job_details["location"] = location_elem.text.strip()
            logger.info(f"Extracted location: {job_details['location']}")
        except Exception as e:
            logger.error(f"Failed to extract location: {e}")
            
        # Extract job description HTML and text
        try:
            # Get the full description HTML
            desc_elem = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((
                    By.CSS_SELECTOR,
                    ".show-more-less-html__markup, " \
                    ".description__text, " \
                    ".jobs-box__html-content"
                ))
            )
            
            # Get the raw description content (including HTML)
            raw_description = desc_elem.get_attribute('outerHTML')
            if not raw_description or len(raw_description.strip()) < 10:  # Fallback to inner HTML if outer is empty
                raw_description = desc_elem.get_attribute('innerHTML')
            
            if raw_description and len(raw_description.strip()) > 10:  # Ensure we have meaningful content
                job_details["raw_description"] = raw_description.strip()
                logger.info(f"Extracted raw job description with {len(raw_description)} characters")
            else:
                logger.warning("Could not extract meaningful job description content")
            
        except Exception as e:
            logger.error(f"Failed to extract job description: {e}")
        
        # Extract number of applicants
        try:
            # Try to find the number of applicants in the top card
            applicants_elem = driver.find_elements(
                By.CSS_SELECTOR,
                ".num-applicants__caption, " \
                "[data-tracking-control-name='public_jobs_topcard-applicant-count'], " \
                "figcaption.num-applicants__caption"
            )
            if applicants_elem:
                applicants_text = applicants_elem[0].text.strip().lower()
                # Extract numeric value from text like "Over 200 applicants" or "200+ applicants"
                import re
                match = re.search(r'(\d+\+?|over\s+\d+)', applicants_text)
                if match:
                    num_applicants = match.group(1).replace('+', '').replace('over', '').strip()
                    if num_applicants.isdigit():
                        job_details["number_of_applicants"] = match.group(1).strip()
                        logger.info(f"Found {match.group(1).strip()} applicants")
        except Exception as e:
            logger.warning(f"Could not extract number of applicants: {e}")
        
        # Extract job metadata (posted date, job type, etc.)
        try:
            # First try to extract from the top card (newer layout)
            meta_items = driver.find_elements(
                By.CSS_SELECTOR,
                ".posted-time-ago__text, " \
                ".jobs-unified-top-card__job-insight, " \
                ".job-flavors__label, " \
                ".topcard__flavor--metadata, " \
                ".description__job-criteria-item, " \
                ".jobs-description-details__list-item, " \
                ".description__job-criteria"
            )
            
            # Try to find the job criteria section (newer layout)
            try:
                criteria_section = driver.find_element(
                    By.CSS_SELECTOR, ".description__job-criteria"
                )
                criteria_items = criteria_section.find_elements(
                    By.CSS_SELECTOR, ".description__job-criteria-item"
                )
                for item in criteria_items:
                    try:
                        label_elem = item.find_element(
                            By.CSS_SELECTOR, 
                            ".description__job-criteria-subheader"
                        )
                        value_elem = item.find_element(
                            By.CSS_SELECTOR,
                            ".description__job-criteria-text"
                        )
                        
                        if label_elem and value_elem:
                            label = label_elem.text.strip().lower()
                            value = value_elem.text.strip()
                            
                            if 'seniority' in label or 'level' in label:
                                job_details["seniority_level"] = value
                            elif 'employment type' in label or 'job type' in label:
                                job_details["employment_type"] = value
                            elif 'skill' in label.lower():
                                job_details["skills"] = str(value) if value is not None else "N/A"
                            elif 'industr' in label.lower():
                                # Store industries as a single string
                                industries_text = value.strip()
                                job_details["industries"] = industries_text
                                logger.info(f"Extracted industries: {industries_text}")
                            elif 'posted' in label and 'date' in label:
                                job_details["posted_date"] = value
                                
                    except Exception as e:
                        logger.debug(f"Error extracting criteria item: {e}")
                        continue
            except Exception as e:
                logger.debug(f"Could not find job criteria section: {e}")
            
            # Process any additional metadata from the top card
            for item in meta_items:
                text = item.text.strip().lower()
                if not text:
                    continue
                    
                # Extract posted date if we haven't found it yet
                if not job_details.get("posted_date") or job_details["posted_date"] == "N/A":
                    if any(x in text for x in ['day', 'week', 'month', 'year', 'hour', 'minute', 'second', 'just now']):
                        job_details["posted_date"] = item.text.strip()
                        continue
                        
                # Try to extract employment type if not found yet
                if not job_details.get("employment_type") or job_details["employment_type"] == "N/A":
                    if any(x in text for x in ['full-time', 'part-time', 'contract', 'temporary', 'internship', 'apprenticeship']):
                        job_details["employment_type"] = item.text.strip()
                        continue
                        
                # Try to extract seniority level if not found yet
                if not job_details.get("seniority_level") or job_details["seniority_level"] == "N/A":
                    if any(x in text for x in ['entry', 'associate', 'mid', 'senior', 'lead', 'principal', 'director', 'vp', 'c-level', 'executive']):
                        job_details["seniority_level"] = item.text.strip()
                        continue
                    
                # Check for employment type
                if any(term in text for term in ['full-time', 'part-time', 'contract', 'internship', 'temporary']):
                    job_details["employment_type"] = text
                # Check for seniority level
                elif any(term in text for term in ['entry', 'associate', 'mid-senior', 'director', 'executive']):
                    job_details["seniority_level"] = text
                # Check for job function
                elif any(term in text for term in ['engineering', 'product', 'design', 'marketing', 'sales']):
                    job_details["job_function"] = text
                # Check for industries
                elif len(text.split(',')) > 1:  # Likely industries
                    job_details["industries"] = str(text)
            
            logger.info(f"Extracted metadata: {job_details.get('employment_type')}, {job_details.get('seniority_level')}")
            
        except Exception as e:
            logger.error(f"Failed to extract metadata: {e}")
        
        # Extract skills if available
        try:
            skills_section = driver.find_elements(
                By.CSS_SELECTOR,
                ".job-details-skill-match-status-list"
            )
            
            if skills_section:
                try:
                    skill_elems = driver.find_elements(
                        By.CSS_SELECTOR,
                        ".description__job-criteria-item--skills .description__job-criteria-text, " \
                        ".job-details-skill-match-status-list__text"
                    )
                    if skill_elems:
                        skills = ", ".join(elem.text.strip() for elem in skill_elems if elem.text.strip())
                        job_details["skills"] = skills
                        logger.info(f"Extracted skills: {skills}")
                except Exception as e:
                    logger.warning(f"Could not extract skills: {e}")
                
        except Exception as e:
            logger.debug(f"No skills section found or error extracting skills: {e}")
        
        # Extract company details if available
        try:
            company_section = driver.find_elements(
                By.CSS_SELECTOR,
                ".company-info"
            )
            
            if company_section:
                company_details = []
                
                # Company size
                size_elem = company_section[0].find_elements(
                    By.CSS_SELECTOR,
                    "[data-test='company-size']"
                )
                if size_elem:
                    size_text = size_elem[0].text.strip()
                    if size_text:
                        company_details.append(f"Size: {size_text}")
                
                # Company website
                website_elem = company_section[0].find_elements(
                    By.CSS_SELECTOR,
                    "a[data-test='company-website']"
                )
                if website_elem:
                    website = website_elem[0].get_attribute('href')
                    if website:
                        company_details.append(f"Website: {website}")
                
                # Join all details with semicolons
                company_details_str = "; ".join(company_details) if company_details else "N/A"
                job_details["company_details"] = company_details_str
                logger.info(f"Extracted company details: {company_details_str}")
                    
        except Exception as e:
            logger.debug(f"No company details section found or error extracting: {e}")
        
        logger.info(f"Successfully extracted job details for: {job_details.get('title', 'N/A')} at {job_details.get('company', 'N/A')}")
        
        return job_details
        
    except Exception as e:
        logger.error(f"Error extracting job description for {job_id}: {str(e)}", exc_info=True)
        return {}
    finally:
        # Clean up the WebDriver
        try:
            driver.quit()
        except Exception as e:
            logger.error(f"Error closing WebDriver: {e}")


@dataclass
class JobPostingExtractor:
    """
    A robust class for extracting job description details from various job posting URLs.
    
    Supports multiple job platforms with fallback mechanisms.
    """
    
    _job_description_cache: BasicInMemoryCache | None = None
    linkedin_cache_key_name = "linkedin_job_id"

    
    def __post_init__(self):       
        if not self._job_description_cache:
            self._job_description_cache = BasicInMemoryCache("linkedin-mcp", 
                                                            "raw_job_description_cache", 
                                                            "raw_job_descriptions.jsonl",
                                                            cache_key_name=self.linkedin_cache_key_name,
                                                            base_cache_dir=f"{os.environ.get('HOME')}/.cache")
        logger.info(f"Raw Description Cache initialized in {self._job_description_cache.cache_file}")
            
            
    def scrape_new_job_ids(self, new_job_ids: List[str], overwrite_cache_entries: bool = False) -> None:
        """
        Scrape job descriptions for new job IDs using multiprocessing.
        
        Args:
            new_job_ids: List of job IDs to scrape
            overwrite_cache_entries: Whether to overwrite existing cache entries
        """
        if not new_job_ids:
            logger.info("No new jobs to scrape")
            return
            
        logger.info(f"Scraping {len(new_job_ids)} new LinkedIn job IDs using multiprocessing")
        start_time = time.time()
        
        # Determine number of processes (use 75% of available CPUs)
        num_processes = max(1, int(cpu_count() * 0.75))
        logger.info(f"Using {num_processes} processes for parallel scraping")
        
        # Create a process pool and map the job IDs to worker processes
        with Pool(processes=num_processes) as pool:
            try:
                # Map job IDs to worker processes
                results = pool.map(extract_job_description_worker, new_job_ids)
                
                # Filter out empty results and save to cache
                valid_results = [job for job in results if job]
                logger.info(f"Successfully scraped {len(valid_results)} out of {len(new_job_ids)} jobs")
                
                # Save to cache
                for job in valid_results:
                    if self._job_description_cache is not None:
                        self._job_description_cache.put(job, overwrite=overwrite_cache_entries)
                
            except Exception as e:
                logger.error(f"Error in parallel job scraping: {e}")
                raise
            finally:
                # Clean up
                pool.close()
                pool.join()
        
        duration = time.time() - start_time
        logger.info(f"Completed parallel scraping in {duration:.2f} seconds")

    def get_scraped_job_ids(self) -> List[str]:
        """Get a list of all job IDs that have already been scraped."""
        if self._job_description_cache is None:
            return []
        return list(self._job_description_cache._cache.keys())
    
    def get_new_job_ids(self, job_ids: List[str]) -> List[str]:
        """
        Filter out job IDs that have already been scraped.
        
        Args:
            job_ids: List of job IDs to check
            
        Returns:
            List of job IDs that haven't been scraped yet
        """            
        scraped_ids = set(self.get_scraped_job_ids())
        logger.info(f"Found {len(scraped_ids)} scraped job IDs")
        logger.debug(f"Scraped job IDs: {scraped_ids}")
        new_job_ids = [job_id for job_id in job_ids if job_id not in scraped_ids]
        
        logger.info(f"Found {len(new_job_ids)} new jobs out of {len(job_ids)} total")
        return new_job_ids

    def retrieve_job_ids_from_linkedin(self, max_pages: int = 5) -> List[str]:
        """
        Retrieve job IDs from LinkedIn using requests and BeautifulSoup.
        
        Args:
            max_pages: Maximum number of pages to scrape
            
        Returns:
            List of job IDs found
        """
        logger.info(f"Starting job retrieval from LinkedIn\n({JOB_RETRIEVAL_URL})")
        start_time = time.time()
        
        all_job_ids: Set[str] = set()
        jobs_per_page = 10
        
        for page in range(max_pages):
            try:
                start_idx = page * jobs_per_page
                url = JOB_RETRIEVAL_URL.format(start_idx)
                logger.info(f"Scraping job listings page {page + 1}: {url}")
                
                # Add random delay between requests
                time.sleep(random.uniform(1, 3))
                
                res = requests.get(url)
                soup = BeautifulSoup(res.text, 'html.parser')
                
                for element in soup.find_all(attrs={"data-entity-urn": True}):
                    if not isinstance(element, bs4.element.Tag):
                        continue
                    entity_urn = element.attrs.get("data-entity-urn")
                    if isinstance(entity_urn, str) and entity_urn.startswith("urn:li:jobPosting:"):
                        job_id = entity_urn.split(":")[-1]
                        if job_id.isdigit():
                            all_job_ids.add(job_id)
                            logger.info(f"Found job ID: {job_id}")
                            
            except Exception as e:
                logger.error(f"Error scraping job listings page {page + 1}: {e}")
                continue
        
        duration = time.time() - start_time
        logger.info(f"Found {len(all_job_ids)} unique job IDs in {duration:.2f} seconds")
        return list(all_job_ids)


# These two URL are the best ones to retrieve jobs without connecting to LinkedIn with your account
JOB_RETRIEVAL_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search-results/?distance=25&geoId=102277331&keywords=Looking%20for%20Research%20Enginer%2FMachine%20Learning%2FAI%20Engineer%20jobs%20in%20San%20Francisco&start={}"
JOB_URL: str = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"


if __name__ == "__main__":
    extractor = JobPostingExtractor()
    
    # Get all job IDs from LinkedIn
    logger.info("Fetching job listings from LinkedIn...")
    all_job_ids = extractor.retrieve_job_ids_from_linkedin(max_pages=2)
    
    # Find only the new job IDs we haven't scraped yet
    new_job_ids = extractor.get_new_job_ids(all_job_ids)
    
    logger.info(f"Found {len(new_job_ids)} new jobs to process")
    
    # test_job_url = JOB_URL.format(job_id="4024185558")
    # test_job_url = JOB_URL.format(job_id="4051266841")
    # test_job_url = JOB_URL.format(job_id="4051266841")
    
    # new_job_ids = ["4024185558"] #, "4051266841", "4051266841"]
    extractor.scrape_new_job_ids(new_job_ids)
