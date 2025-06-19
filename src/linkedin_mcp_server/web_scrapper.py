import asyncio
import os
import random
import time
import urllib
import urllib.parse
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

import bs4
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from loguru import logger
from selenium import webdriver
from selenium.common.exceptions import (
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
    WebDriverException,
)
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


def get_linkedin_credentials() -> tuple[str, str]:
    """
    Retrieve LinkedIn credentials from environment variables.
    
    Returns:
        tuple: (username, password)
    
    Raises:
        ValueError: If credentials are not set
    """
    username = os.getenv('LINKEDIN_USERNAME')
    password = os.getenv('LINKEDIN_PASSWORD')
    
    if not username or not password:
        raise ValueError("LinkedIn credentials must be set in .env file")
    return username, password


@dataclass
class JobPostingExtractor:
    """
    A robust class for extracting job description details from various job posting URLs.
    
    Supports multiple job platforms with fallback mechanisms.
    """
    
    username: str | None = None
    password: str | None = None
    timeout: int = 10
    _job_description_cache: BasicInMemoryCache | None = None
    _driver: WebDriver | None = None
    client_id = os.getenv('LINKEDIN_OAUTH_CLIENT_ID')
    client_secret = os.getenv('LINKEDIN_OAUTH_CLIENT_SECRET')
    redirect_uri = "http://localhost:8000/callback"
    scope = "r_liteprofile r_emailaddress"
    
    linkedin_cache_key_name = "linkedin_job_id"

    
    def __post_init__(self):
        self.auth_url = (
            f"https://www.linkedin.com/oauth/v2/authorization"
            f"?response_type=code"
            f"&client_id={self.client_id}"
            f"&redirect_uri={urllib.parse.quote(self.redirect_uri)}"
            f"&scope={urllib.parse.quote(self.scope)}"
        )
        logger.info(self.auth_url)                
        self._driver, self.oauth_code = self._setup_webdriver()
        self._driver.implicitly_wait(self.timeout)
        logger.info("WebDriver initialized")
        
        if not self._job_description_cache:
            self._job_description_cache = BasicInMemoryCache("linkedin-mcp", 
                                                            "raw_job_description_cache", 
                                                            "raw_job_descriptions.jsonl",
                                                            cache_key_name=self.linkedin_cache_key_name)
        logger.info(f"Raw Description Cache initialized in {self._job_description_cache.cache_file}")
        
        # Perform login if credentials are provided
        # self._linkedin_login(*get_linkedin_credentials())
            
            
    def _setup_webdriver(self) -> Tuple[WebDriver, str]:
        """
        Setup Chrome webdriver with headless mode and common options
        
        Returns:
            Configured Chrome webdriver
        """
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        # chrome_options.add_argument(r"--user-data-dir=/Users/fperez/Library/Application Support/Google/LinkedInMCP")
        # chrome_options.add_argument("--profile-directory=Default")  # or "Profile 1", etc.        
        
        try:
            driver = webdriver.Chrome(options=chrome_options)
            # logger.info(f"Navigating to {self.auth_url}")
            # driver.get(self.auth_url)
            
            # # print(driver.page_source)
            
            # time.sleep(2)
            # logger.info(f"Setting username, password and clicking submit...")
            # username, password = get_linkedin_credentials()
            # driver.find_element(By.ID, "username").send_keys(username)
            # driver.find_element(By.ID, "password").send_keys(password)
            # driver.find_element(By.XPATH, "//button[@type='submit']").click()
            # logger.info("Waiting for redirect...")
            # while True:
            #     current_url = driver.current_url
            #     if "code=" in current_url:
            #         break
            #     time.sleep(1)
            # parsed_url = urllib.parse.urlparse(current_url)
            # oauth_code = urllib.parse.parse_qs(parsed_url.query).get("code")[0]
            
            return driver, "" #oauth_code
        except Exception as e:
            logger.error(f"Failed to initialize webdriver: {e}")
            raise        
        
    
    
    def _linkedin_login(self, username: str, password: str):
        """
        Perform LinkedIn login with the provided credentials
        
        Args:
            username (str): LinkedIn username
            password (str): LinkedIn password
        """
        
        try:
            # Navigate to LinkedIn login page
            self._driver.get("https://www.linkedin.com/login")
            
            # Wait for page to load
            time.sleep(3)
            
            # Find and fill username field
            username_field = self._driver.find_element(By.ID, "username")
            username_field.clear()
            username_field.send_keys(username)
            
            # Find and fill password field
            password_field = self._driver.find_element(By.ID, "password")
            password_field.clear()
            password_field.send_keys(password)
            
            # Submit login form
            password_field.submit()
            
            # Wait for potential login challenges
            time.sleep(5)
            logger.info(f"LinkedIn login submitted for user: {username}")
            
            # Optional: Check if login was successful
            try:
                # Look for an element that exists only after successful login
                self._driver.find_element(By.CSS_SELECTOR, "div.feed-identity-module")
                logger.info(f"LinkedIn login successful for user: {username}")
            except Exception:
                logger.warning("Login might have failed or requires additional verification")
        
        except Exception as e:
            logger.error(f"Failed to perform LinkedIn login: {e}")
            raise
        
    def parse_job(self, job_element):
        title_element = job_element.find('a', class_='job-card-search__link--Oj6')
        logger.info(f"Title element {title_element}")
        if title_element:
            title = title_element.text.strip()
            url = title_element['href']
            company_element = job_element.find('a', class_='job-card-container__company-name')
            company = company_element.text.strip() if company_element else "N/A"
            return {
                'title': title,
                'company': company,
                'url': url
            }
        return None    
    
    def extract_raw_job_data(self, job_ids: List[str]):
        for job_id in job_ids:
            job_url: str = self.job_url.format(job_id=job_id)
            job_data: Tuple[Dict[str, str], bool] = self.extract_raw_info_from(job_url)
            print(job_data)
            if job_data:
                self._job_description_cache.put(job_data[0])
    
    async def scrape_job_listings_page(self, url: str, start_idx: int) -> List[str]:
        
        delay = random.uniform(0, 1)
        await asyncio.sleep(delay)
        
        try:
            url = url.format(start_idx)
            logger.info(f"Scraping job listings page {start_idx}: {url}")
            res = requests.get(url)
            soup=BeautifulSoup(res.text,'html.parser')
            job_ids: Set[str] = set()
            for element in soup.find_all(attrs={"data-entity-urn": True}):
                if not isinstance(element, bs4.element.Tag):
                    continue
                entity_urn = element.attrs.get("data-entity-urn")
                if isinstance(entity_urn, str) and entity_urn.startswith("urn:li:jobPosting:"):
                    job_id = entity_urn.split(":")[-1]
                    if job_id.isdigit():
                        job_ids.add(job_id)
                        logger.info(f"Found job ID: {job_id}")
            return list(job_ids)
        except Exception as e:
            logger.error(f"Error scraping job listings page: {e}")
            return []
    
    
    async def scrape_job_listings(self, url: str, max_pages: int = 5, jobs_per_page: int = 10) -> List[str]:
        """
        Extract job IDs from LinkedIn job search results using requests+BeautifulSoup.
        Looks for job IDs in data-entity-urn attributes with format urn:li:jobPosting:4250736028.
        
        Args:
            url: The base URL with a {} placeholder for page number
            max_pages: Maximum number of pages to scrape (each page contains multiple jobs)
            
        Returns:
            List of unique job IDs found across all pages
        """

        # Create scrapping tasks for all pages (each page contains 10 jobs in the JOB_RETRIEVAL_URL above)
        tasks = [self.scrape_job_listings_page(url, i * jobs_per_page) for i in range(max_pages)]
        
        # Run all tasks concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Combine results from all pages
        job_ids: Set[str] = set()
        for result in results:
            if isinstance(result, list):
                job_ids.update(result)
            elif isinstance(result, Exception):
                logger.error(f"Error in page scrape: {result}")
        
        logger.info(f"Total unique job IDs found: {len(job_ids)}")
        return list(job_ids)
            


    def retrieve_job_ids_from_linkedin(self, max_pages: int = 5) -> List[str]:
        """
        Retrieve job IDs from LinkedIn asynchronously.
        This method starts the scraping in the background and returns immediately.
        
        Returns:
            List of job IDs found during scraping
        """
        logger.info(f"Starting async job retrieval from LinkedIn\n({JOB_RETRIEVAL_URL})")
        start_time = time.time()        
        all_jobs = asyncio.run(self.scrape_job_listings(JOB_RETRIEVAL_URL, max_pages))        
        duration = time.time() - start_time
        logger.info(f"Scraped {len(all_jobs)} jobs in {duration:.2f} seconds")
        return all_jobs


    def extract_linkedin_job_description(self, url: str) -> Dict[str, str]:
        """
        Extract job description from LinkedIn job posting with caching
        
        Args:
            url (str): LinkedIn job posting URL
        
        Returns:
            Dict containing job details or empty dict if extraction fails
        """
        try:            
            self._driver.get(url)
            logger.info(f"Navigated to {url}")
            
            # Wait for the page to load
            WebDriverWait(self._driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".top-card-layout__title, .job-details-jobs-unified-top-card__job-title"))
            )
            
            # Initialize job details with default values
            job_details = {
                self.linkedin_cache_key_name: url.split("/")[-1],
                "title": "N/A",
                "company": "N/A",
                "location": "N/A",
                "employment_type": "N/A",
                "workplace_type": "N/A",
                "description": "N/A",
                "posted_date": "N/A",
                "applicants": "N/A",
                "seniority_level": "N/A",
                "job_function": "N/A",
                "industries": "N/A"
            }
            
            # Extract job title
            try:
                title_elem = self._driver.find_element(
                    By.CSS_SELECTOR, 
                    ".top-card-layout__title, .job-details-jobs-unified-top-card__job-title"
                )
                job_details["title"] = title_elem.text.strip()
            except Exception as e:
                logger.error(f"Failed to extract job title: {e}")
            
            # Extract company name
            try:
                company_elem = self._driver.find_element(
                    By.CSS_SELECTOR,
                    "a.topcard__org-name-link, .job-details-jobs-unified-top-card__company-name a"
                )
                job_details["company"] = company_elem.text.strip()
            except Exception as e:
                logger.error(f"Failed to extract company name: {e}")
                
            # Extract location
            try:
                location_elem = self._driver.find_element(
                    By.CSS_SELECTOR,
                    ".topcard__flavor--bullet, .job-details-jobs-unified-top-card__bullet"
                )
                job_details["location"] = location_elem.text.strip()
            except Exception as e:
                logger.error(f"Failed to extract location: {e}")
                
            # Extract job description
            try:
                # First try the main content area
                desc_elem = self._driver.find_element(
                    By.CSS_SELECTOR,
                    ".description__text .show-more-less-html__markup, " \
                    ".jobs-box__html-content, .jobs-description-content__text"
                )
                html_content = desc_elem.get_attribute('innerHTML')
                job_details["description"] = html_content.strip() if html_content else ""
            except Exception as e:
                logger.error(f"Failed to extract job description: {e}")
                try:
                    # Fallback to any element with the job description class
                    desc_elem = self._driver.find_element(
                        By.CLASS_NAME,
                        "jobs-description__content"
                    )
                    job_details["description"] = desc_elem.text.strip()
                except Exception as e:
                    logger.error(f"Failed to extract job description (fallback): {e}")
            
            # Extract additional job details
            try:
                # Look for details in the job criteria section
                criteria_items = self._driver.find_elements(
                    By.CSS_SELECTOR,
                    ".description__job-criteria-item"
                )
                
                for item in criteria_items:
                    try:
                        label = item.find_element(By.CSS_SELECTOR, ".description__job-criteria-subheader").text.strip()
                        value = item.find_element(By.CSS_SELECTOR, ".description__job-criteria-text").text.strip()
                        
                        if 'seniority level' in label.lower():
                            job_details["seniority_level"] = value
                        elif 'employment type' in label.lower():
                            job_details["employment_type"] = value
                        elif 'job function' in label.lower():
                            job_details["job_function"] = value
                        elif 'industries' in label.lower():
                            job_details["industries"] = value
                    except Exception as e:
                        logger.error(f"Failed to extract job criteria: {e}")
            except Exception as e:
                logger.error(f"Failed to find job criteria section: {e}")
            
            # Extract posted date and applicants if available
            try:
                meta_info = self._driver.find_elements(
                    By.CSS_SELECTOR,
                    ".posted-time-ago__text, .jobs-unified-top-card__job-insight"
                )
                logger.info(meta_info[0].text)
                logger.info(meta_info[1].text)
                if len(meta_info) > 0:
                    job_details["posted_date"] = meta_info[0].text.strip()
                if len(meta_info) > 1:
                    job_details["applicants"] = meta_info[1].text.strip()
            except Exception as e:
                logger.error(f"Failed to extract meta information: {e}")
            
            logger.info(f"Successfully extracted job details for: {job_details.get('title', 'N/A')} at {job_details.get('company', 'N/A')}")
            logger.info(job_details)
            return job_details
            
        except Exception as e:
            logger.error(f"Error extracting job description from {url}: {e}")
            return {}
            
    def extract_raw_info_from(self, url: str) -> Tuple[Dict[str, str], bool]:
        """
        Main extraction method with platform-specific logic using pattern matching
        
        Args:
            url (str): The URL to extract job details from
        
        Returns:
            Extracted job details and whether it was a cache hit or not
        """

        # Check cache first
        cached_job = self._job_description_cache.get(url) if self._job_description_cache is not None else None
        if cached_job:
            logger.info(f"Retrieved job description from cache: {url}")
            return cached_job, True
        
        return self.extract_linkedin_job_description(url, *get_linkedin_credentials()), False

    def get_scraped_job_ids(self) -> List[str]:
        """Get a list of all job IDs that have already been scraped."""
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


# These two URL are the best ones to retrieve jobs without connecting to LinkedIn with your account
JOB_RETRIEVAL_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search-results/?distance=25&geoId=102277331&keywords=Looking%20for%20Research%20Enginer%2FMachine%20Learning%2FAI%20Engineer%20jobs%20in%20San%20Francisco&start={}"

# job_url = "https://www.linkedin.com/jobs/view/{job_id}/"
JOB_URL: str = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"


if __name__ == "__main__":
    extractor = JobPostingExtractor()
    
    # Get all job IDs from LinkedIn
    logger.info("Fetching job listings from LinkedIn...")
    # all_job_ids = extractor.retrieve_job_ids_from_linkedin(max_pages=3)
    
    # # Find only the new job IDs we haven't scraped yet
    # new_job_ids = extractor.get_new_job_ids(all_job_ids)
    
    # logger.info(f"Found {len(new_job_ids)} new jobs to process")
    
    test_job_url = JOB_URL.format(job_id="4051266841")
    logger.info(f"Testing job URL: {test_job_url}")
    extractor.extract_linkedin_job_description(test_job_url)
    
    # if new_job_ids:
    #     logger.info(f"Found {len(new_job_ids)} new jobs to process")
    #     # Process only the new jobs
    #     # extractor.extract_raw_job_data(new_job_ids)
    # else:
    #     logger.info("No new jobs found to process")
