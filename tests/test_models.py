"""Tests for Pydantic response models"""

import pytest
from pydantic import ValidationError

from linkedin_mcp_server.models import (
    JobApplicationTracking,
    JobBenefits,
    JobCompanyEnrichment,
    JobCompleteSkills,
    JobCore,
    JobDecisionMaking,
    JobDescriptionInsights,
    JobEmploymentDetails,
    JobFullDescription,
    JobMetadata,
    JobResponse,
)


def test_job_core_required_fields():
    """Test JobCore with all required fields"""
    core = JobCore(
        job_id="123",
        title="ML Engineer",
        company="Anthropic",
        location="San Francisco, CA",
        posted_date="2 days ago",
        posted_date_iso="2026-02-13T10:00:00Z",
    )

    assert core.job_id == "123"
    assert core.title == "ML Engineer"
    assert core.company == "Anthropic"
    assert core.location == "San Francisco, CA"
    assert core.posted_date == "2 days ago"
    assert core.posted_date_iso == "2026-02-13T10:00:00Z"


def test_job_core_missing_fields():
    """Test JobCore raises error when required fields missing"""
    with pytest.raises(ValidationError):
        JobCore(job_id="123", title="ML Engineer")


def test_job_decision_making_defaults():
    """Test JobDecisionMaking with default values"""
    decision = JobDecisionMaking()

    assert decision.salary_range is None
    assert decision.remote_eligible is False
    assert decision.visa_sponsorship is False
    assert decision.applicants is None
    assert decision.easy_apply is False


def test_job_decision_making_custom_values():
    """Test JobDecisionMaking with custom values"""
    decision = JobDecisionMaking(
        salary_range="$150K - $200K",
        remote_eligible=True,
        visa_sponsorship=True,
        applicants="50-100 applicants",
        easy_apply=True,
    )

    assert decision.salary_range == "$150K - $200K"
    assert decision.remote_eligible is True
    assert decision.visa_sponsorship is True
    assert decision.applicants == "50-100 applicants"
    assert decision.easy_apply is True


def test_job_description_insights_defaults():
    """Test JobDescriptionInsights with default values"""
    insights = JobDescriptionInsights()

    assert insights.description_summary is None
    assert insights.key_requirements == []
    assert insights.key_responsibilities_preview is None


def test_job_description_insights_custom_values():
    """Test JobDescriptionInsights with custom values"""
    insights = JobDescriptionInsights(
        description_summary="Seeking ML Engineer...",
        key_requirements=["Python", "TensorFlow", "5+ years experience"],
        key_responsibilities_preview="Build ML pipelines",
    )

    assert insights.description_summary == "Seeking ML Engineer..."
    assert len(insights.key_requirements) == 3
    assert "Python" in insights.key_requirements
    assert insights.key_responsibilities_preview == "Build ML pipelines"


def test_job_application_tracking():
    """Test JobApplicationTracking model"""
    tracking = JobApplicationTracking(
        application_status="applied",
        applied_at="2026-02-10T10:00:00Z",
        application_notes="Applied via LinkedIn",
    )

    assert tracking.application_status == "applied"
    assert tracking.applied_at == "2026-02-10T10:00:00Z"
    assert tracking.application_notes == "Applied via LinkedIn"


def test_job_company_enrichment():
    """Test JobCompanyEnrichment model"""
    enrichment = JobCompanyEnrichment(
        company_size="1000-5000 employees",
        company_industry="Artificial Intelligence",
        company_description="AI safety and research",
        company_website="https://anthropic.com",
        company_headquarters="San Francisco, CA",
        company_founded=2021,
        company_specialties=["AI Safety", "LLMs", "Alignment"],
    )

    assert enrichment.company_size == "1000-5000 employees"
    assert enrichment.company_founded == 2021
    assert len(enrichment.company_specialties) == 3


def test_job_metadata():
    """Test JobMetadata model"""
    metadata = JobMetadata(
        job_url="https://linkedin.com/jobs/view/123",
        scraped_at="2026-02-15T10:00:00Z",
        last_seen="2026-02-15T10:00:00Z",
        seniority_level="Entry level",
        employment_type="Full-time",
    )

    assert metadata.job_url == "https://linkedin.com/jobs/view/123"
    assert metadata.seniority_level == "Entry level"
    assert metadata.employment_type == "Full-time"


def test_job_full_description():
    """Test JobFullDescription model"""
    desc = JobFullDescription(description="We are seeking an ML Engineer...")

    assert desc.description == "We are seeking an ML Engineer..."


def test_job_complete_skills():
    """Test JobCompleteSkills model"""
    skills = JobCompleteSkills(
        skills_required=["Python", "TensorFlow"],
        skills_preferred=["PyTorch", "AWS"],
    )

    assert len(skills.skills_required) == 2
    assert len(skills.skills_preferred) == 2
    assert "Python" in skills.skills_required


def test_job_benefits():
    """Test JobBenefits model"""
    benefits = JobBenefits(benefits=["Health insurance", "401(k)", "Remote work"])

    assert len(benefits.benefits) == 3
    assert "Remote work" in benefits.benefits


def test_job_employment_details():
    """Test JobEmploymentDetails model"""
    details = JobEmploymentDetails(
        workplace_type="Remote",
        experience_level="Mid-Senior level",
        industry="Technology",
    )

    assert details.workplace_type == "Remote"
    assert details.experience_level == "Mid-Senior level"
    assert details.industry == "Technology"


def test_job_response_minimal():
    """Test JobResponse with only required sections (core + decision_making)"""
    core = JobCore(
        job_id="123",
        title="ML Engineer",
        company="Anthropic",
        location="San Francisco, CA",
        posted_date="2 days ago",
        posted_date_iso="2026-02-13T10:00:00Z",
    )
    decision = JobDecisionMaking(remote_eligible=True)

    response = JobResponse(core=core, decision_making=decision)

    assert response.core.job_id == "123"
    assert response.decision_making.remote_eligible is True
    assert response.description_insights is None
    assert response.application_tracking is None
    assert response.company_enrichment is None
    assert response.metadata is None
    assert response.full_description is None
    assert response.complete_skills is None
    assert response.benefits is None
    assert response.employment_details is None


def test_job_response_full():
    """Test JobResponse with all sections"""
    core = JobCore(
        job_id="123",
        title="ML Engineer",
        company="Anthropic",
        location="San Francisco, CA",
        posted_date="2 days ago",
        posted_date_iso="2026-02-13T10:00:00Z",
    )
    decision = JobDecisionMaking(
        salary_range="$150K - $200K",
        remote_eligible=True,
        visa_sponsorship=True,
        applicants="50-100 applicants",
        easy_apply=True,
    )
    insights = JobDescriptionInsights(
        description_summary="Seeking ML Engineer...",
        key_requirements=["Python", "TensorFlow"],
        key_responsibilities_preview="Build ML pipelines",
    )
    tracking = JobApplicationTracking(application_status="applied")
    enrichment = JobCompanyEnrichment(company_size="1000-5000 employees")
    metadata = JobMetadata(seniority_level="Entry level")
    full_desc = JobFullDescription(description="Full description...")
    skills = JobCompleteSkills(skills_required=["Python"])
    benefits = JobBenefits(benefits=["Health insurance"])
    emp_details = JobEmploymentDetails(workplace_type="Remote")

    response = JobResponse(
        core=core,
        decision_making=decision,
        description_insights=insights,
        application_tracking=tracking,
        company_enrichment=enrichment,
        metadata=metadata,
        full_description=full_desc,
        complete_skills=skills,
        benefits=benefits,
        employment_details=emp_details,
    )

    assert response.core.job_id == "123"
    assert response.decision_making.remote_eligible is True
    assert response.description_insights.description_summary == "Seeking ML Engineer..."
    assert response.application_tracking.application_status == "applied"
    assert response.company_enrichment.company_size == "1000-5000 employees"
    assert response.metadata.seniority_level == "Entry level"
    assert response.full_description.description == "Full description..."
    assert response.complete_skills.skills_required == ["Python"]
    assert response.benefits.benefits == ["Health insurance"]
    assert response.employment_details.workplace_type == "Remote"


def test_job_response_serialization_exclude_none():
    """Test JobResponse serialization with exclude_none=True"""
    core = JobCore(
        job_id="123",
        title="ML Engineer",
        company="Anthropic",
        location="San Francisco, CA",
        posted_date="2 days ago",
        posted_date_iso="2026-02-13T10:00:00Z",
    )
    decision = JobDecisionMaking(remote_eligible=True)
    insights = JobDescriptionInsights(description_summary="Seeking ML Engineer...")

    response = JobResponse(
        core=core, decision_making=decision, description_insights=insights
    )

    # Serialize with exclude_none=True
    data = response.model_dump(exclude_none=True)

    # Verify core and decision_making are present
    assert "core" in data
    assert "decision_making" in data
    assert "description_insights" in data

    # Verify None optional sections are excluded
    assert "application_tracking" not in data
    assert "company_enrichment" not in data
    assert "metadata" not in data
    assert "full_description" not in data
    assert "complete_skills" not in data
    assert "benefits" not in data
    assert "employment_details" not in data


def test_job_response_serialization_include_all():
    """Test JobResponse serialization without exclude_none"""
    core = JobCore(
        job_id="123",
        title="ML Engineer",
        company="Anthropic",
        location="San Francisco, CA",
        posted_date="2 days ago",
        posted_date_iso="2026-02-13T10:00:00Z",
    )
    decision = JobDecisionMaking(remote_eligible=True)

    response = JobResponse(core=core, decision_making=decision)

    # Serialize without exclude_none
    data = response.model_dump()

    # Verify all fields are present (including None values)
    assert "core" in data
    assert "decision_making" in data
    assert "description_insights" in data
    assert data["description_insights"] is None
    assert "application_tracking" in data
    assert data["application_tracking"] is None
