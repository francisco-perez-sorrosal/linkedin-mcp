from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from linkedin_mcp_server.scraper import (
    JobDetail,
    JobSummary,
    parse_job_detail_page,
    parse_search_card,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def search_card_html():
    """Load search card HTML fixture"""
    return (FIXTURES_DIR / "search_card.html").read_text()


@pytest.fixture
def detail_page_html():
    """Load detail page HTML fixture"""
    return (FIXTURES_DIR / "detail_page.html").read_text()


def test_parse_search_card(search_card_html):
    """Test parsing a search result card"""
    soup = BeautifulSoup(search_card_html, "html.parser")
    card = soup.select_one("li.base-card")

    summary = parse_search_card(card)

    assert isinstance(summary, JobSummary)
    assert summary.job_id == "4271043001"
    assert summary.title == "ML Engineer"
    assert summary.company == "Instawork"
    assert "instawork" in summary.company_url.lower()
    assert summary.location == "San Francisco, CA"
    assert summary.posted_date == "2 days ago"
    assert summary.posted_date_iso == "2026-01-29"
    assert "4271043001" in summary.job_url
    assert summary.benefits_badge == "Actively Hiring"


def test_parse_search_card_missing_fields():
    """Test parsing a card with missing elements returns sensible defaults"""
    # Empty card
    html = '<li class="base-card"></li>'
    soup = BeautifulSoup(html, "html.parser")
    card = soup.select_one("li.base-card")

    summary = parse_search_card(card)

    assert isinstance(summary, JobSummary)
    assert summary.job_id == "N/A"
    assert summary.title == "N/A"
    assert summary.company == "N/A"


def test_parse_job_detail_page(detail_page_html):
    """Test parsing a job detail page"""
    job_id = "4271043001"
    detail = parse_job_detail_page(detail_page_html, job_id)

    assert isinstance(detail, JobDetail)
    assert detail.job_id == job_id
    assert detail.source == "linkedin"
    assert detail.title == "ML Engineer"
    assert detail.company == "Instawork"
    assert "instawork" in detail.company_url.lower()
    assert detail.location == "San Francisco, CA"
    assert detail.posted_date == "2 days ago"
    assert detail.number_of_applicants == "Over 200 applicants"
    assert "$160,000" in detail.salary
    assert "We are seeking an innovative ML Engineer" in detail.raw_description
    assert "Entry level" in detail.seniority_level
    assert "Full-time" in detail.employment_type
    assert "Engineering" in detail.job_function
    assert "Technology" in detail.industries


def test_parse_job_detail_page_partial():
    """Test detail page with missing optional fields returns N/A"""
    # Minimal HTML with only required fields
    html = """
    <div>
      <h2 class="top-card-layout__title">Test Job</h2>
    </div>
    """
    job_id = "123"
    detail = parse_job_detail_page(html, job_id)

    assert isinstance(detail, JobDetail)
    assert detail.job_id == job_id
    assert detail.title == "Test Job"
    assert detail.company == "N/A"
    assert detail.salary == "N/A"
    assert detail.skills == "N/A"
    assert detail.company_details == "N/A"


def test_parse_job_detail_page_invalid_html():
    """Test parsing invalid HTML gracefully"""
    html = "<div>Invalid</div>"
    job_id = "999"
    detail = parse_job_detail_page(html, job_id)

    assert isinstance(detail, JobDetail)
    assert detail.job_id == job_id
    # Most fields should be N/A since selectors won't match
    assert detail.company == "N/A"
    assert detail.location == "N/A"
