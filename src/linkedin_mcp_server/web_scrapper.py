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


    def extract_linkedin_job_description(self, url: str) -> Dict[str, Any]:
        """
        Extract job description and metadata from LinkedIn job posting
        
        Args:
            url (str): LinkedIn job posting URL
            
        Returns:
            Dict containing job details or empty dict if extraction fails
        """
        if self._driver is None:
            logger.error("WebDriver is not initialized")
            return {}
            
        try:            
            self._driver.get(url)
            logger.info(f"Navigated to {url}")
            
            # Initialize job details with default values and URL
            job_id = url.strip('/').split('/')[-1]
            job_details = {
                self.linkedin_cache_key_name: job_id,
                "url": url,
                "source": "linkedin",
                "scraped_at": datetime.now().isoformat(),
                "title": "N/A",
                "company": "N/A",
                "location": "N/A",
                "description": "N/A",
                "description_html": "N/A",
                "posted_date": "N/A",
                "job_type": "N/A",
                "employment_type": "N/A",
                "seniority_level": "N/A",
                "job_function": "N/A",
                "industries": [],
                "skills": [],
                "company_details": {}
            }
            
            # Extract job title
            try:
                title_elem = self._driver.find_element(
                    By.CSS_SELECTOR,
                    ".top-card-layout__title, .topcard__title"
                )
                job_details["title"] = title_elem.text.strip()
                logger.info(f"Extracted job title: {job_details['title']}")
            except Exception as e:
                logger.error(f"Failed to extract job title: {e}")
            
            # Extract company name and URL
            try:
                company_elem = self._driver.find_element(
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
                location_elem = self._driver.find_element(
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
                desc_elem = WebDriverWait(self._driver, 10).until(
                    EC.presence_of_element_located((
                        By.CSS_SELECTOR,
                        ".show-more-less-html__markup, " \
                        ".description__text, " \
                        ".jobs-box__html-content"
                    ))
                )
                
                # Get the HTML content
                html_content = desc_elem.get_attribute('outerHTML')
                if html_content:
                    job_details["description_html"] = html_content
                    
                    # Get clean text content
                    text_content = desc_elem.text.strip()
                    job_details["description"] = text_content
                    
                    logger.info(f"Extracted job description with {len(text_content)} characters")
                
            except Exception as e:
                logger.error(f"Failed to extract job description: {e}")
            
            # Extract job metadata (posted date, job type, etc.)
            try:
                # First try to extract from the top card (newer layout)
                meta_items = self._driver.find_elements(
                    By.CSS_SELECTOR,
                    ".posted-time-ago__text, " \
                    ".jobs-unified-top-card__job-insight, " \
                    ".job-flavors__label, " \
                    ".topcard__flavor--metadata, " \
                    ".description__job-criteria-item"
                )
                
                # Try to find the job criteria section (newer layout)
                try:
                    criteria_section = self._driver.find_element(
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
                                elif 'function' in label:
                                    job_details["job_function"] = value
                                elif 'industr' in label:
                                    job_details["industries"] = [i.strip() for i in value.split(',')]
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
                        job_details["industries"] = [i.strip() for i in text.split(',')]
                
                logger.info(f"Extracted metadata: {job_details.get('employment_type')}, {job_details.get('seniority_level')}")
                
            except Exception as e:
                logger.error(f"Failed to extract metadata: {e}")
            
            # Extract skills if available
            try:
                skills_section = self._driver.find_elements(
                    By.CSS_SELECTOR,
                    ".job-details-skill-match-status-list"
                )
                
                if skills_section:
                    skill_elements = skills_section[0].find_elements(
                        By.CSS_SELECTOR,
                        "span.job-details-skill-match-status-list__pill-text"
                    )
                    job_details["skills"] = [s.text.strip() for s in skill_elements if s.text.strip()]
                    logger.info(f"Extracted {len(job_details['skills'])} skills")
                    
            except Exception as e:
                logger.debug(f"No skills section found or error extracting skills: {e}")
            
            # Extract company details if available
            try:
                company_section = self._driver.find_elements(
                    By.CSS_SELECTOR,
                    ".company-info"
                )
                
                if company_section:
                    company_details = {}
                    
                    # Company size
                    size_elem = company_section[0].find_elements(
                        By.CSS_SELECTOR,
                        "[data-test='company-size']"
                    )
                    if size_elem:
                        company_details["size"] = size_elem[0].text.strip()
                    
                    # Company website
                    website_elem = company_section[0].find_elements(
                        By.CSS_SELECTOR,
                        "a[data-test='company-website']"
                    )
                    if website_elem:
                        company_details["website"] = website_elem[0].get_attribute('href')
                    
                    if company_details:
                        job_details["company_details"] = company_details
                        logger.info(f"Extracted company details: {company_details}")
                        
            except Exception as e:
                logger.debug(f"No company details section found or error extracting: {e}")
            
            logger.info(f"Successfully extracted job details for: {job_details.get('title', 'N/A')} at {job_details.get('company', 'N/A')}")
            logger.debug(f"Job details: {job_details}")
            
            # Save to cache if cache is enabled
            if hasattr(self, '_job_description_cache') and self._job_description_cache is not None:
                try:
                    self._job_description_cache.put(job_details)
                except Exception as e:
                    logger.warning(f"Failed to cache job details: {e}")
                
            return job_details
            
        except Exception as e:
            logger.error(f"Error extracting job description from {url}: {str(e)}", exc_info=True)
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
        
        return self.extract_linkedin_job_description(url), False

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
    
    test_job_url = JOB_URL.format(job_id="4024185558")
    logger.info(f"Testing job URL: {test_job_url}")
    extractor.extract_linkedin_job_description(test_job_url)
    
    # if new_job_ids:
    #     logger.info(f"Found {len(new_job_ids)} new jobs to process")
    #     # Process only the new jobs
    #     # extractor.extract_raw_job_data(new_job_ids)
    # else:
    #     logger.info("No new jobs found to process")
