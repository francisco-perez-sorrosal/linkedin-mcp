from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from linkedin_mcp_server.scraper import (
    JobDetail,
    JobSummary,
    extract_description_insights,
    extract_remote_eligibility,
    extract_salary_structured,
    extract_skills,
    extract_visa_sponsorship,
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
    assert detail.skills == []  # Changed from "N/A" to [] since skills is now list[str]
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


# ========== Salary Parsing Tests (Step 5) ==========


def test_extract_salary_structured_basic_range():
    """Test basic salary range with K suffix."""
    result = extract_salary_structured("$120K - $180K")
    assert result["min"] == 120000
    assert result["max"] == 180000
    assert result["currency"] == "USD"
    assert result["equity_offered"] is False


def test_extract_salary_structured_comma_separated():
    """Test salary range with comma-separated numbers."""
    result = extract_salary_structured("$150,000 - $200,000")
    assert result["min"] == 150000
    assert result["max"] == 200000
    assert result["currency"] == "USD"
    assert result["equity_offered"] is False


def test_extract_salary_structured_lowercase_k():
    """Test salary range with lowercase k suffix."""
    result = extract_salary_structured("120-180k")
    assert result["min"] == 120000
    assert result["max"] == 180000
    assert result["currency"] == "USD"


def test_extract_salary_structured_single_value():
    """Test single salary value."""
    result = extract_salary_structured("$150K")
    assert result["min"] == 150000
    assert result["max"] == 150000
    assert result["currency"] == "USD"


def test_extract_salary_structured_equity():
    """Test equity detection."""
    result = extract_salary_structured("$150K + equity")
    assert result["min"] == 150000
    assert result["max"] == 150000
    assert result["equity_offered"] is True


def test_extract_salary_structured_rsu():
    """Test RSU equity detection."""
    result = extract_salary_structured("$200,000/yr + RSU")
    assert result["min"] == 200000
    assert result["max"] == 200000
    assert result["equity_offered"] is True


def test_extract_salary_structured_stock_options():
    """Test stock options equity detection."""
    result = extract_salary_structured("Base $180K + stock options")
    assert result["min"] == 180000
    assert result["max"] == 180000
    assert result["equity_offered"] is True


def test_extract_salary_structured_euro():
    """Test Euro currency detection."""
    result = extract_salary_structured("€60K - €80K")
    assert result["min"] == 60000
    assert result["max"] == 80000
    assert result["currency"] == "EUR"
    assert result["equity_offered"] is False


def test_extract_salary_structured_gbp():
    """Test GBP currency detection."""
    result = extract_salary_structured("£50K - £70K")
    assert result["min"] == 50000
    assert result["max"] == 70000
    assert result["currency"] == "GBP"


def test_extract_salary_structured_na():
    """Test N/A input."""
    result = extract_salary_structured("N/A")
    assert result["min"] is None
    assert result["max"] is None
    assert result["currency"] == "USD"
    assert result["equity_offered"] is False


def test_extract_salary_structured_empty():
    """Test empty input."""
    result = extract_salary_structured("")
    assert result["min"] is None
    assert result["max"] is None
    assert result["currency"] == "USD"


def test_extract_salary_structured_none():
    """Test None input."""
    result = extract_salary_structured(None)
    assert result["min"] is None
    assert result["max"] is None


def test_extract_salary_structured_invalid():
    """Test invalid input with no numbers."""
    result = extract_salary_structured("Competitive salary")
    assert result["min"] is None
    assert result["max"] is None


# ========== Remote/Visa/Skills/Description Insights Tests (Step 6) ==========


def test_extract_remote_eligibility_positive():
    """Test remote eligibility detection with positive keywords."""
    assert extract_remote_eligibility("We offer remote work opportunities") is True
    assert extract_remote_eligibility("This is a fully remote position") is True
    assert extract_remote_eligibility("Work from home available") is True
    assert extract_remote_eligibility("Remote-first company") is True


def test_extract_remote_eligibility_negative():
    """Test remote eligibility with no remote keywords."""
    assert extract_remote_eligibility("On-site only position") is False
    assert extract_remote_eligibility("Must be in office 5 days a week") is False
    assert extract_remote_eligibility("N/A") is False
    assert extract_remote_eligibility("") is False


def test_extract_visa_sponsorship_positive():
    """Test visa sponsorship detection with positive keywords."""
    assert extract_visa_sponsorship("H1B sponsorship available") is True
    assert extract_visa_sponsorship("We sponsor H-1B visas") is True
    assert extract_visa_sponsorship("Visa support provided") is True
    assert extract_visa_sponsorship("Can sponsor work authorization") is True


def test_extract_visa_sponsorship_negative():
    """Test visa sponsorship with no sponsorship keywords."""
    assert extract_visa_sponsorship("Great benefits and competitive salary") is False
    assert extract_visa_sponsorship("Join our amazing team") is False
    assert extract_visa_sponsorship("N/A") is False
    assert extract_visa_sponsorship("") is False


def test_extract_skills_programming_languages():
    """Test extracting programming languages."""
    description = "Experience with Python, Java, and TypeScript required"
    skills = extract_skills(description)
    assert "Python" in skills
    assert "Java" in skills
    assert "Typescript" in skills


def test_extract_skills_ml_frameworks():
    """Test extracting ML frameworks."""
    description = "TensorFlow, PyTorch, and scikit-learn experience needed"
    skills = extract_skills(description)
    assert "Tensorflow" in skills
    assert "Pytorch" in skills
    assert "Scikit-Learn" in skills


def test_extract_skills_cloud_platforms():
    """Test extracting cloud platforms."""
    description = "AWS, GCP, and Azure experience required"
    skills = extract_skills(description)
    assert "AWS" in skills
    assert "GCP" in skills
    assert "Azure" in skills


def test_extract_skills_databases():
    """Test extracting database skills."""
    description = "PostgreSQL, MongoDB, and Redis experience"
    skills = extract_skills(description)
    assert "Postgresql" in skills
    assert "Mongodb" in skills
    assert "Redis" in skills


def test_extract_skills_devops():
    """Test extracting DevOps tools."""
    description = "Docker, Kubernetes, and Terraform required"
    skills = extract_skills(description)
    assert "Docker" in skills
    assert "Kubernetes" in skills
    assert "Terraform" in skills


def test_extract_skills_empty():
    """Test extracting skills from empty or N/A description."""
    assert extract_skills("") == []
    assert extract_skills("N/A") == []
    assert extract_skills("No technical skills mentioned") == []


def test_extract_skills_sorted():
    """Test that extracted skills are sorted."""
    description = "Python, AWS, Docker, Kubernetes, TensorFlow"
    skills = extract_skills(description)
    assert skills == sorted(skills)


def test_extract_description_insights_full():
    """Test extracting insights from a full job description."""
    description = """We are seeking an ML Engineer with 5+ years of experience.
Build scalable ML pipelines using Python and TensorFlow.
Design robust data infrastructure.
Develop automated testing frameworks.
A Master's degree in Computer Science is required."""

    insights = extract_description_insights(description)

    # Check summary (first 300 chars)
    assert insights["description_summary"] is not None
    assert len(insights["description_summary"]) <= 300
    assert "ML Engineer" in insights["description_summary"]

    # Check requirements extraction
    requirements = insights["key_requirements"]
    assert any("5+ years" in req for req in requirements)
    assert any("Master" in req or "MS" in req for req in requirements)
    assert "Python" in requirements or "Tensorflow" in requirements  # Skills

    # Check responsibilities preview
    resp_preview = insights["key_responsibilities_preview"]
    assert resp_preview is not None
    assert "Build" in resp_preview or "Design" in resp_preview or "Develop" in resp_preview


def test_extract_description_insights_empty():
    """Test extracting insights from empty description."""
    insights = extract_description_insights("")
    assert insights["description_summary"] is None
    assert insights["key_requirements"] == []
    assert insights["key_responsibilities_preview"] is None


def test_extract_description_insights_na():
    """Test extracting insights from N/A description."""
    insights = extract_description_insights("N/A")
    assert insights["description_summary"] is None
    assert insights["key_requirements"] == []
    assert insights["key_responsibilities_preview"] is None


def test_extract_description_insights_short():
    """Test extracting insights from short description (< 300 chars)."""
    description = "Looking for a data scientist with Python and SQL experience."
    insights = extract_description_insights(description)

    # Short description should return as-is
    assert insights["description_summary"] == description
    assert "Python" in insights["key_requirements"]
