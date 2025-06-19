from dataclasses import dataclass
from datetime import datetime
import math
import os
import time
from typing import Any, Dict, List, Optional, Tuple
import urllib
import requests
import urllib.parse

from bs4 import BeautifulSoup
from dotenv import load_dotenv
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
import bs4


from linkedin_mcp_server.cache import BasicInMemoryCache

from loguru import logger


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
            self._job_description_cache = BasicInMemoryCache("auto-cv", 
                                                            "raw_job_description_cache", 
                                                            "raw_job_descriptions.jsonl",
                                                            cache_key_name="url")
        logger.info(f"Raw Description Cache initialized in {self._job_description_cache.cache_file}")
        
        # Perform login if credentials are provided
        self._linkedin_login(*get_linkedin_credentials())
        # self.username, self.password = get_linkedin_credentials()
        # if self.username and self.password:
        #     try:
        #         self._linkedin_login(self.username, self.password)
        #         logger.info(f"Logged into LinkedIn as {self.username}")
        #     except Exception as e:
        #         logger.error(f"Login failed: {e}")
        #         raise e
        # else:
        #     logger.info("No LinkedIn credentials provided")
        #     raise ValueError("LinkedIn credentials must be set in .env file")
            
            
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
    
    
    job_retrieve_url = "https://www.linkedin.com/jobs/search-results/?keywords=Looking%20for%20Research%20Enginer%2FMachine%20Learning%2FAI%20Engineer%20jobs%20in%20San%20Francisco"
    job_retrieve_url = "https://www.linkedin.com/jobs/search?keywords=ai+engineer%2Fmachine+learning+research+engineer+in+san+francisco&location=United+States&geoId=103644278"
    job_retrieve_url = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search-results/?distance=25&geoId=102277331&keywords=Looking%20for%20Research%20Enginer%2FMachine%20Learning%2FAI%20Engineer%20jobs%20in%20San%20Francisco&start={}"
    
    job_url = "https://www.linkedin.com/jobs/view/{job_id}/"
    
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
    
    def scrape_job_listings(self, url: str) -> List[str]:
        """
        Extract job IDs from LinkedIn job search results using requests+BeautifulSoup.
        Looks for job IDs in data-entity-urn attributes with format urn:li:jobPosting:4250736028.
        """
        job_ids = set()
        try:
            job_list = set()
            step = 10
            # for i in range(0, math.ceil(1000/step), step):
            #     time.sleep(2)
            #     res = requests.get(url.format(i))
            #     soup=BeautifulSoup(res.text,'html.parser')
            #     alljobs_on_this_page=soup.find_all("li")

            #     logger.info(f"Jobs Page: {len(alljobs_on_this_page)}")

            #     for x in range(0,len(alljobs_on_this_page)):
            #         jobid = alljobs_on_this_page[x].find("div",{"class":"base-card"}).get('data-entity-urn').split(":")[3]
            #         job_list.add(jobid)
            
            # print(job_list)
            
            # job_list = list(job_list)
            # print(len(job_list))
            # exit()
           
            
            # # Save main page source
            # with open('main_page.html', 'w', encoding='utf-8') as f:
            #     f.write(self._driver.page_source)
            # exit()
            logger.info(math.ceil(1000/step))
            for i in range(0, 300, step):
                logger.info(f"Start at {i}")
                time.sleep(1)
                res = requests.get(url.format(i))
                soup=BeautifulSoup(res.text,'html.parser')

                # Extract from `data-entity-urn` attribute (format: urn:li:jobPosting:4250736028)
                for element in soup.find_all(attrs={"data-entity-urn": True}):
                    if not isinstance(element, bs4.element.Tag):
                        continue
                    entity_urn = element.attrs.get("data-entity-urn")
                    if isinstance(entity_urn, str) and entity_urn.startswith("urn:li:jobPosting:"):
                        job_id = entity_urn.split(":")[-1]
                        if job_id.isdigit():
                            job_ids.add(job_id)
                            logger.info(f"Found job ID: {job_id}")
            
            logger.info(f"Total job IDs found: {len(job_ids)}")
            return list(job_ids)
            
        except Exception as e:
            logger.error(f"Error extracting job listings: {e}")
            return []


    def retrieve_recommended_jobs_from_linkedin(self) -> None:
        """
        Retrieve recommended jobs from LinkedIn
        """
        all_jobs = []
        logger.info(f"Retrieving recommended jobs from LinkedIn {self.job_retrieve_url}")
        scraped_jobs: List[str] = self.scrape_job_listings(self.job_retrieve_url)
        logger.info(f"Scraped {len(scraped_jobs)} jobs")
        self.extract_raw_job_data(scraped_jobs[:1])


    def extract_linkedin_job_description(self, 
                                         url: str, 
                                         username: str | None = None, 
                                         password: str | None = None) -> Dict[str, str]:
        """
        Extract job description from LinkedIn job posting with caching
        
        Args:
            url (str): LinkedIn job posting URL
            username (str, optional): LinkedIn username for login
            password (str, optional): LinkedIn password for login
        
        Returns:
            Dict containing job details or empty dict if extraction fails
        """        
        
        try:            
            self._driver.get(url)
            logger.info(f"Navigated to {url}")
                        
            job_title = "N/A"
            job_title_selectors = [
                (By.CSS_SELECTOR, "h1.top-card-layout__title"),
            ]
            # Try these selectors one by one
            for selector in job_title_selectors:
                if self._driver is None:
                    logger.error("WebDriver is None, cannot extract job title.")
                    break
                try:
                    element = WebDriverWait(self._driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "h1.top-card-layout__title"))
                    )
                    job_title = element.text
                    logger.info(f"SUCCESS with selector {selector}: {job_title}")
                    break
                except Exception as e:
                    logger.error(f"FAILED to extract job title with selector {selector}: {e}")
                    
                
            logger.debug(f"Job title: {job_title}")
            
            # Extract company name using an array of selectors (only the correct one for now)
            company_selectors = [
                (By.CSS_SELECTOR, "a.topcard__org-name-link"),
            ]
            company_name = "N/A"
            for selector in company_selectors:
                if self._driver is None:
                    logger.error("WebDriver is None, cannot extract company name.")
                    break
                try:
                    company_element = WebDriverWait(self._driver, 10).until(
                        EC.presence_of_element_located(selector)
                    )
                    company_name = company_element.text
                    logger.info(f"SUCCESS with selector {selector}: {company_name}")
                    break
                except Exception as e:
                    logger.error(f"FAILED to extract company name with selector {selector}: {e}")
                    
            
            # Define multiple potential selectors for job description
            job_desc_selectors = [
                (By.CSS_SELECTOR, "div.show-more-less-html__markup"),
            ]
            
            job_description = "N/A"
            # Try multiple selectors to find job description
            for selector in job_desc_selectors:
                if self._driver is None:
                    logger.error("WebDriver is None, cannot extract job description.")
                    break
                logger.info(f"Trying selector {selector}")
                try:
                    elements = self._driver.find_elements(*selector)
                    if elements:
                        job_desc_element = elements[0]
                        # Try to get the full HTML content for formatting
                        html_content = job_desc_element.get_attribute('innerHTML')
                        if html_content and html_content.strip():
                            job_description = html_content.strip()
                        else:
                            job_description = job_desc_element.text.strip()
                        break
                except Exception as e:
                    logger.warning(f"Selector {selector} failed: {e}")
            
            # Extract salary/pay figures using an array of selectors (CSS only)
            salary_selectors = [
                (By.CSS_SELECTOR, "div.compensation__salary"),
            ]
            salary = "N/A"
            for selector in salary_selectors:
                if self._driver is None:
                    logger.error("WebDriver is None, cannot extract salary.")
                    break
                try:
                    salary_element = WebDriverWait(self._driver, 2).until(
                        EC.presence_of_element_located(selector)
                    )
                    salary = salary_element.text
                    logger.info(f"SUCCESS with selector {selector}: {salary}")
                    break
                except Exception as e:
                    logger.error(f"FAILED to extract salary with selector {selector}: {e}")

            # Extract salary/pay comments using an array of selectors (CSS only)
            salary_comments_selectors = [
                (By.CSS_SELECTOR, "p.compensation__description"),
            ]
            salary_comments = "N/A"
            for selector in salary_comments_selectors:
                if self._driver is None:
                    logger.error("WebDriver is None, cannot extract salary comments.")
                    break
                try:
                    comments_element = WebDriverWait(self._driver, 2).until(
                        EC.presence_of_element_located(selector)
                    )
                    salary_comments = comments_element.text
                    logger.info(f"SUCCESS with selector {selector}: {salary_comments}")
                    break
                except Exception as e:
                    logger.error(f"FAILED to extract salary comments with selector {selector}: {e}")

            job_details = {
                "title": job_title.strip(),
                "company": company_name.strip(),
                "salary": salary.strip() if salary else "N/A",
                "salary_comments": salary_comments.strip() if salary_comments else "N/A",
                "raw_description": job_description.strip(),
                "url": url,
                "extracted_at": datetime.now().isoformat()
            }
            
            # Save to cache
            if self._job_description_cache is not None:
                self._job_description_cache.put(job_details)
            
            return job_details
        
        except Exception as e:
            logger.error(f"Job description extraction failed: {e}")
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


if __name__ == "__main__":
    url = "https://www.linkedin.com/jobs/collections/recommended/?currentJobId=3959722886"
    url = "https://www.linkedin.com/jobs/collections/recommended/?currentJobId=4070067137"
    
    extractor = JobPostingExtractor()
    job_details = extractor.retrieve_recommended_jobs_from_linkedin()
    # job_details = extractor.extract_raw_info_from(url)
    print(job_details)