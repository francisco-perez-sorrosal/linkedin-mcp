"""Async HTTP scraper for LinkedIn job postings"""

import asyncio
import random
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

import httpx
from bs4 import BeautifulSoup, Tag
from loguru import logger

# URL constants
SEARCH_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search-results/"
DETAIL_URL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"

# HTTP headers
DEFAULT_HEADERS = {
    "Accept": "text/html",
    "Accept-Language": "en-US,en;q=0.9",
}

# User agents for rotation
USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
]

# CSS selectors
SELECTORS = {
    # Search card selectors
    "search_card": "li.base-card",
    "card_title": "h3.base-search-card__title",
    "card_company": "h4.base-search-card__subtitle a",
    "card_company_url": "h4.base-search-card__subtitle a[href]",
    "card_location": "span.job-search-card__location",
    "card_posted_date": "time.job-search-card__listdate",
    "card_posted_date_iso": "time.job-search-card__listdate[datetime]",
    "card_job_url": "a.base-card__full-link[href]",
    "card_entity_urn": "[data-entity-urn]",
    "card_benefits": "span.job-posting-benefits__text",

    # Detail page selectors
    "detail_title": "h2.top-card-layout__title",
    "detail_company": "a.topcard__org-name-link",
    "detail_company_url": "a.topcard__org-name-link[href]",
    "detail_location": "span.topcard__flavor--bullet",
    "detail_posted_date": "span.posted-time-ago__text",
    "detail_applicants": "figcaption.num-applicants__caption",
    "detail_salary": "div.salary.compensation__salary",
    "detail_description": "div.show-more-less-html__markup, div.description__text",
    "detail_job_criteria": "li.description__job-criteria-item",
}


@dataclass(frozen=True)
class JobSummary:
    """Summary data from a LinkedIn search result card"""
    job_id: str
    title: str
    company: str
    company_url: str
    location: str
    posted_date: str
    posted_date_iso: str
    job_url: str
    benefits_badge: str


@dataclass(frozen=True)
class JobDetail:
    """Full metadata from a LinkedIn job detail page"""
    job_id: str
    url: str
    source: str
    scraped_at: str
    title: str
    company: str
    company_url: str
    location: str
    posted_date: str
    posted_date_iso: str
    number_of_applicants: str
    salary: str
    raw_description: str
    employment_type: str
    seniority_level: str
    job_function: str
    industries: str
    skills: list[str]  # Changed from str to list[str]
    company_details: str

    # New enhanced fields (Step 7)
    salary_min: float | None
    salary_max: float | None
    salary_currency: str
    equity_offered: bool
    remote_eligible: bool
    visa_sponsorship: bool
    easy_apply: bool
    normalized_company_name: str


def parse_search_card(card: Tag) -> JobSummary:
    """Extract summary fields from a search result card element

    Args:
        card: BeautifulSoup Tag element representing a job card

    Returns:
        JobSummary with extracted fields
    """
    try:
        # Extract job ID from data-entity-urn attribute (check card itself or child elements)
        job_id = "N/A"
        urn = card.get("data-entity-urn")
        if not urn:
            # Check child elements if not on card itself
            urn_element = card.select_one(SELECTORS["card_entity_urn"])
            if urn_element:
                urn = urn_element.get("data-entity-urn")

        if urn and "urn:li:jobPosting:" in str(urn):
            job_id = str(urn).split(":")[-1]

        # Extract other fields with fallbacks
        title_el = card.select_one(SELECTORS["card_title"])
        title = title_el.get_text(strip=True) if title_el else "N/A"

        company_el = card.select_one(SELECTORS["card_company"])
        company = company_el.get_text(strip=True) if company_el else "N/A"

        company_url_el = card.select_one(SELECTORS["card_company_url"])
        company_url = company_url_el.get("href", "N/A") if company_url_el else "N/A"

        location_el = card.select_one(SELECTORS["card_location"])
        location = location_el.get_text(strip=True) if location_el else "N/A"

        posted_date_el = card.select_one(SELECTORS["card_posted_date"])
        posted_date = posted_date_el.get_text(strip=True) if posted_date_el else "N/A"

        posted_date_iso_el = card.select_one(SELECTORS["card_posted_date_iso"])
        posted_date_iso = posted_date_iso_el.get("datetime", "N/A") if posted_date_iso_el else "N/A"

        job_url_el = card.select_one(SELECTORS["card_job_url"])
        job_url = job_url_el.get("href", "N/A") if job_url_el else "N/A"

        benefits_el = card.select_one(SELECTORS["card_benefits"])
        benefits_badge = benefits_el.get_text(strip=True) if benefits_el else "N/A"

        return JobSummary(
            job_id=job_id,
            title=title,
            company=company,
            company_url=str(company_url),
            location=location,
            posted_date=posted_date,
            posted_date_iso=str(posted_date_iso),
            job_url=str(job_url),
            benefits_badge=benefits_badge,
        )
    except Exception as e:
        logger.error(f"Error parsing search card: {e}")
        return JobSummary(
            job_id="N/A",
            title="N/A",
            company="N/A",
            company_url="N/A",
            location="N/A",
            posted_date="N/A",
            posted_date_iso="N/A",
            job_url="N/A",
            benefits_badge="N/A",
        )


def parse_job_detail_page(html: str, job_id: str) -> JobDetail:
    """Extract all metadata fields from a job detail HTML fragment

    Args:
        html: HTML content of the job detail page
        job_id: LinkedIn job ID

    Returns:
        JobDetail with extracted fields
    """
    soup = BeautifulSoup(html, "html.parser")
    url = DETAIL_URL.format(job_id=job_id)

    try:
        # Extract basic fields
        title_el = soup.select_one(SELECTORS["detail_title"])
        title = title_el.get_text(strip=True) if title_el else "N/A"

        company_el = soup.select_one(SELECTORS["detail_company"])
        company = company_el.get_text(strip=True) if company_el else "N/A"

        company_url_el = soup.select_one(SELECTORS["detail_company_url"])
        company_url = company_url_el.get("href", "N/A") if company_url_el else "N/A"

        location_el = soup.select_one(SELECTORS["detail_location"])
        location = location_el.get_text(strip=True) if location_el else "N/A"

        posted_date_el = soup.select_one(SELECTORS["detail_posted_date"])
        posted_date = posted_date_el.get_text(strip=True) if posted_date_el else "N/A"

        applicants_el = soup.select_one(SELECTORS["detail_applicants"])
        applicants = applicants_el.get_text(strip=True) if applicants_el else "N/A"

        salary_el = soup.select_one(SELECTORS["detail_salary"])
        salary = salary_el.get_text(strip=True) if salary_el else "N/A"

        description_el = soup.select_one(SELECTORS["detail_description"])
        raw_description = str(description_el) if description_el else "N/A"

        # Extract job criteria (seniority, employment type, function, industries)
        criteria_items = soup.select(SELECTORS["detail_job_criteria"])
        seniority = "N/A"
        employment_type = "N/A"
        job_function = "N/A"
        industries = "N/A"

        for item in enumerate(criteria_items):
            header = item[1].select_one("h3")
            value = item[1].select_one("span")
            if header and value:
                header_text = header.get_text(strip=True)
                value_text = value.get_text(strip=True)

                if "seniority" in header_text.lower():
                    seniority = f"{header_text}\n{value_text}"
                elif "employment" in header_text.lower():
                    employment_type = f"{header_text}\n{value_text}"
                elif "function" in header_text.lower():
                    job_function = f"{header_text.lower()}\n{value_text}"
                elif "industries" in header_text.lower():
                    industries = f"{header_text.lower()}\n{value_text}"

        # Extract enhanced metadata using extraction functions (Step 7)
        from linkedin_mcp_server.db import normalize_company_name

        # Parse salary structure
        salary_data = extract_salary_structured(salary)

        # Extract from description
        description_text = description_el.get_text(strip=True) if description_el else "N/A"
        skills_list = extract_skills(description_text)
        remote = extract_remote_eligibility(description_text)
        visa = extract_visa_sponsorship(description_text)

        # Detect easy apply (check for easy apply badge/button)
        easy_apply_el = soup.select_one(".jobs-apply-button--top-card") or soup.select_one("[aria-label*='Easy Apply']")
        easy_apply = easy_apply_el is not None

        # Get posted_date_iso (extract from posted_date_el if datetime attribute exists)
        # Try to get ISO date from datetime attribute, fall back to posted_date text
        posted_date_el = soup.select_one(SELECTORS["detail_posted_date"])
        posted_date_iso_raw = posted_date_el.get("datetime") if posted_date_el and hasattr(posted_date_el, "get") else None
        posted_date_iso = str(posted_date_iso_raw) if posted_date_iso_raw else posted_date

        return JobDetail(
            job_id=job_id,
            url=url,
            source="linkedin",
            scraped_at=datetime.now().isoformat(),
            title=title,
            company=company,
            company_url=str(company_url),
            location=location,
            posted_date=posted_date,
            posted_date_iso=posted_date_iso,
            number_of_applicants=applicants,
            salary=salary,
            raw_description=raw_description,
            employment_type=employment_type,
            seniority_level=seniority,
            job_function=job_function,
            industries=industries,
            skills=skills_list,
            company_details="N/A",  # Not reliably available in guest API
            # Enhanced fields
            salary_min=salary_data["min"],
            salary_max=salary_data["max"],
            salary_currency=salary_data["currency"],
            equity_offered=salary_data["equity_offered"],
            remote_eligible=remote,
            visa_sponsorship=visa,
            easy_apply=easy_apply,
            normalized_company_name=normalize_company_name(company),
        )
    except Exception as e:
        logger.error(f"Error parsing job detail for {job_id}: {e}")
        return JobDetail(
            job_id=job_id,
            url=url,
            source="linkedin",
            scraped_at=datetime.now().isoformat(),
            title="N/A",
            company="N/A",
            company_url="N/A",
            location="N/A",
            posted_date="N/A",
            posted_date_iso="N/A",
            number_of_applicants="N/A",
            salary="N/A",
            raw_description="N/A",
            employment_type="N/A",
            seniority_level="N/A",
            job_function="N/A",
            industries="N/A",
            skills=[],
            company_details="N/A",
            # Enhanced fields - safe defaults
            salary_min=None,
            salary_max=None,
            salary_currency="USD",
            equity_offered=False,
            remote_eligible=False,
            visa_sponsorship=False,
            easy_apply=False,
            normalized_company_name="N/A",
        )


def create_client(timeout: float = 30.0) -> httpx.AsyncClient:
    """Create an httpx.AsyncClient with connection pooling and rotating UA

    Args:
        timeout: Request timeout in seconds

    Returns:
        Configured AsyncClient
    """
    headers = DEFAULT_HEADERS.copy()
    headers["User-Agent"] = random.choice(USER_AGENTS)

    return httpx.AsyncClient(
        headers=headers,
        timeout=timeout,
        follow_redirects=True,
    )


async def request_with_backoff(
    client: httpx.AsyncClient,
    url: str,
    semaphore: asyncio.Semaphore,
    max_retries: int = 3,
    base_delay: float = 1.0,
) -> httpx.Response:
    """GET with semaphore, random delay, and exponential backoff on 429/503

    Args:
        client: httpx AsyncClient
        url: URL to fetch
        semaphore: asyncio Semaphore for concurrency control
        max_retries: Maximum retry attempts
        base_delay: Base delay in seconds for exponential backoff

    Returns:
        httpx.Response

    Raises:
        httpx.HTTPStatusError: If request fails after retries
    """
    async with semaphore:
        # Random delay to avoid rate limiting
        await asyncio.sleep(random.uniform(1.0, 3.0))

        for attempt in range(max_retries):
            try:
                response = await client.get(url)

                # Check for rate limiting
                if response.status_code in (429, 503):
                    if attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt)
                        logger.warning(f"Rate limited (status {response.status_code}), retrying after {delay}s...")
                        await asyncio.sleep(delay)
                        continue

                response.raise_for_status()
                return response

            except httpx.HTTPStatusError as e:
                if attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt)
                    logger.warning(f"HTTP error {e.response.status_code}, retrying after {delay}s...")
                    await asyncio.sleep(delay)
                    continue
                raise
            except httpx.RequestError as e:
                if attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt)
                    logger.warning(f"Request error: {e}, retrying after {delay}s...")
                    await asyncio.sleep(delay)
                    continue
                raise

        # Should not reach here
        raise RuntimeError(f"Failed to fetch {url} after {max_retries} attempts")


async def search_jobs_pages(
    client: httpx.AsyncClient,
    query: str,
    location: str,
    distance: int,
    num_pages: int,
    filters: dict[str, str] | None = None,
) -> list[JobSummary]:
    """Fetch search result pages and parse job cards into summary data

    Args:
        client: httpx AsyncClient
        query: Job search query
        location: Job location
        distance: Search radius in miles
        num_pages: Number of pages to fetch
        filters: Optional filter parameters (experience_level, job_type, etc.)

    Returns:
        List of JobSummary objects
    """
    summaries: list[JobSummary] = []

    for page in range(num_pages):
        start = page * 10

        # Build URL
        params = {
            "keywords": query,
            "location": location,
            "distance": str(distance),
            "start": str(start),
        }

        # Add optional filters
        if filters:
            params.update(filters)

        # Construct query string manually to avoid encoding issues
        query_string = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{SEARCH_URL}?{query_string}"

        try:
            # No semaphore for search pages (low rate of requests)
            response = await client.get(url)
            response.raise_for_status()

            # Parse cards
            soup = BeautifulSoup(response.text, "html.parser")
            cards = soup.select(SELECTORS["search_card"])

            for card in cards:
                summary = parse_search_card(card)
                if summary.job_id != "N/A":
                    summaries.append(summary)

            logger.info(f"Parsed {len(cards)} jobs from page {page + 1}")

            # Random delay between pages
            if page < num_pages - 1:
                await asyncio.sleep(random.uniform(1.0, 3.0))

        except Exception as e:
            logger.error(f"Error fetching search page {page + 1}: {e}")
            continue

    return summaries


async def fetch_single_job_detail(
    client: httpx.AsyncClient,
    job_id: str,
    semaphore: asyncio.Semaphore,
) -> JobDetail:
    """Fetch and parse a single job detail page with rate limiting and retry

    Args:
        client: httpx AsyncClient
        job_id: LinkedIn job ID
        semaphore: asyncio Semaphore for concurrency control

    Returns:
        JobDetail object
    """
    url = DETAIL_URL.format(job_id=job_id)

    try:
        response = await request_with_backoff(client, url, semaphore)
        return parse_job_detail_page(response.text, job_id)
    except Exception as e:
        logger.error(f"Error fetching job detail {job_id}: {e}")
        # Return a minimal JobDetail on error
        return JobDetail(
            job_id=job_id,
            url=url,
            source="linkedin",
            scraped_at=datetime.now().isoformat(),
            title="N/A",
            company="N/A",
            company_url="N/A",
            location="N/A",
            posted_date="N/A",
            posted_date_iso="N/A",
            number_of_applicants="N/A",
            salary="N/A",
            raw_description="N/A",
            employment_type="N/A",
            seniority_level="N/A",
            job_function="N/A",
            industries="N/A",
            skills=[],
            company_details="N/A",
            # Enhanced fields - safe defaults
            salary_min=None,
            salary_max=None,
            salary_currency="USD",
            equity_offered=False,
            remote_eligible=False,
            visa_sponsorship=False,
            easy_apply=False,
            normalized_company_name="N/A",
        )


async def fetch_job_details(
    client: httpx.AsyncClient,
    job_ids: list[str],
    semaphore: asyncio.Semaphore,
) -> list[JobDetail]:
    """Fetch detail pages for multiple job IDs with concurrency control

    Args:
        client: httpx AsyncClient
        job_ids: List of LinkedIn job IDs
        semaphore: asyncio Semaphore for concurrency control

    Returns:
        List of JobDetail objects
    """
    tasks = [fetch_single_job_detail(client, job_id, semaphore) for job_id in job_ids]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Filter out exceptions and return valid results
    details = []
    for result in results:
        if isinstance(result, JobDetail):
            details.append(result)
        elif isinstance(result, Exception):
            logger.error(f"Exception during detail fetch: {result}")

    return details


# ========== Enhanced Extraction Functions (Phase 2) ==========


def extract_salary_structured(salary_text: str) -> dict:
    """
    Parse salary text into structured min/max/currency/equity.

    Examples:
        "$120K - $180K" → {"min": 120000, "max": 180000, "currency": "USD", "equity_offered": False}
        "$150,000/yr + equity" → {"min": 150000, "max": 150000, "currency": "USD", "equity_offered": True}
        "€60K - €80K" → {"min": 60000, "max": 80000, "currency": "EUR", "equity_offered": False}

    Args:
        salary_text: Raw salary text from job posting

    Returns:
        Dictionary with min, max, currency, and equity_offered
    """
    import re

    result = {"min": None, "max": None, "currency": "USD", "equity_offered": False}

    if not salary_text or salary_text == "N/A":
        return result

    # Detect equity
    equity_keywords = ["equity", "stock options", "rsu", "options", "stock"]
    result["equity_offered"] = any(kw in salary_text.lower() for kw in equity_keywords)

    # Detect currency
    currency_map = {
        "$": "USD",
        "£": "GBP",
        "€": "EUR",
        "¥": "JPY",
    }
    for symbol, code in currency_map.items():
        if symbol in salary_text:
            result["currency"] = code
            break

    # Extract numbers (handle K/k suffix and commas)
    # Pattern: optional currency symbol, digits, optional comma, optional K/k
    pattern = r'[\$£€¥]?\s*(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*[Kk]?'
    matches = re.findall(pattern, salary_text)

    if not matches:
        return result

    # Parse matches
    nums = []
    for match in matches:
        # Remove commas
        num_str = match.replace(',', '')
        num = float(num_str)

        # Check if K/k suffix present in original text
        if 'k' in salary_text.lower():
            # Heuristic: if number < 1000, assume it's in thousands
            if num < 1000:
                num *= 1000

        nums.append(int(num))

    # Assign min/max
    if len(nums) == 1:
        result["min"] = nums[0]
        result["max"] = nums[0]
    elif len(nums) >= 2:
        result["min"] = min(nums[0], nums[1])
        result["max"] = max(nums[0], nums[1])

    return result


def extract_remote_eligibility(description: str) -> bool:
    """
    Detect remote work keywords in job description.

    Args:
        description: Raw job description text

    Returns:
        True if remote keywords found, False otherwise
    """
    if not description or description == "N/A":
        return False

    desc_lower = description.lower()
    remote_keywords = [
        "remote", "work from home", "wfh", "distributed", "anywhere",
        "fully remote", "remote-first", "remote work", "work remotely"
    ]

    return any(kw in desc_lower for kw in remote_keywords)


def extract_visa_sponsorship(description: str) -> bool:
    """
    Detect visa sponsorship keywords in job description.

    Args:
        description: Raw job description text

    Returns:
        True if visa sponsorship keywords found, False otherwise
    """
    if not description or description == "N/A":
        return False

    desc_lower = description.lower()
    visa_keywords = [
        "visa sponsorship", "h1b", "h-1b", "work authorization",
        "sponsorship available", "sponsor visa", "visa support",
        "eligible for visa", "can sponsor"
    ]

    return any(kw in desc_lower for kw in visa_keywords)


def extract_skills(description: str) -> list[str]:
    """
    Extract common tech skills from job description (best-effort).

    Args:
        description: Raw job description text

    Returns:
        Sorted list of detected skills
    """
    import re

    if not description or description == "N/A":
        return []

    # Common tech skills to look for
    skill_patterns = [
        # Programming languages
        r'\bPython\b', r'\bJava\b', r'\bC\+\+\b', r'\bGo\b', r'\bRust\b',
        r'\bJavaScript\b', r'\bTypeScript\b', r'\bScala\b', r'\bKotlin\b',

        # ML/AI frameworks
        r'\bTensorFlow\b', r'\bPyTorch\b', r'\bKeras\b', r'\bscikit-learn\b',
        r'\bHugging\s*Face\b', r'\bLangChain\b', r'\bOpenAI\b',

        # Cloud platforms
        r'\bAWS\b', r'\bGCP\b', r'\bGoogle\s*Cloud\b', r'\bAzure\b',

        # Databases
        r'\bPostgreSQL\b', r'\bMySQL\b', r'\bMongoDB\b', r'\bRedis\b',
        r'\bSQLite\b', r'\bCassandra\b',

        # DevOps/Tools
        r'\bDocker\b', r'\bKubernetes\b', r'\bTerraform\b', r'\bGit\b',
        r'\bCI/CD\b', r'\bJenkins\b', r'\bGitHub\s*Actions\b',

        # Data tools
        r'\bSpark\b', r'\bAirflow\b', r'\bKafka\b', r'\bdbt\b',
        r'\bPandas\b', r'\bNumPy\b',
    ]

    found_skills = set()

    for pattern in skill_patterns:
        matches = re.findall(pattern, description, re.IGNORECASE)
        for match in matches:
            # Normalize capitalization (preserve original casing for acronyms)
            if match.isupper() and len(match) <= 4:
                found_skills.add(match.upper())
            else:
                found_skills.add(match.title())

    return sorted(list(found_skills))


def extract_description_insights(description_text: str) -> dict:
    """
    Extract summary and key requirements from job description for composable responses.

    Args:
        description_text: Raw job description text

    Returns:
        Dictionary with description_summary, key_requirements, and key_responsibilities_preview
    """
    import re

    if not description_text or description_text == "N/A":
        return {
            "description_summary": None,
            "key_requirements": [],
            "key_responsibilities_preview": None
        }

    # Summary: first 300 chars (or first 2-3 sentences)
    summary = description_text[:300].rsplit('.', 1)[0] + '.' if len(description_text) > 300 else description_text

    # Extract key requirements
    requirements = []

    # Years of experience
    exp_match = re.search(r'(\d+)\+?\s*years?\s*(of\s*)?(experience|exp)', description_text, re.I)
    if exp_match:
        requirements.append(f"{exp_match.group(1)}+ years experience")

    # Degree requirements
    degree_patterns = [r'(MS|Master|PhD|Doctorate|Bachelor|BS|BA)\s*(degree)?', r'(Graduate|Undergraduate)\s*degree']
    for pattern in degree_patterns:
        match = re.search(pattern, description_text, re.I)
        if match:
            requirements.append(match.group(0))
            break

    # Top skills (limit to 5)
    found_skills = extract_skills(description_text)
    requirements.extend(found_skills[:5])

    # Key responsibilities (extract sentences starting with action verbs)
    resp_verbs = ['Build', 'Design', 'Develop', 'Lead', 'Manage', 'Deploy', 'Create', 'Implement']
    responsibilities = []
    for line in description_text.split('\n'):
        for verb in resp_verbs:
            if line.strip().startswith(verb):
                responsibilities.append(line.strip()[:80])
                break

    return {
        "description_summary": summary,
        "key_requirements": requirements,
        "key_responsibilities_preview": " • ".join(responsibilities[:3]) if responsibilities else None
    }
