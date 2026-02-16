"""Pydantic models for composable job response API"""

from pydantic import BaseModel, Field


class JobCore(BaseModel):
    """Core job identification (always included)."""

    job_id: str
    title: str
    company: str
    location: str
    posted_date: str
    posted_date_iso: str


class JobDecisionMaking(BaseModel):
    """Decision-making fields (always included)."""

    salary_range: str | None = None
    remote_eligible: bool = False
    visa_sponsorship: bool = False
    applicants: str | None = None
    easy_apply: bool = False


class JobDescriptionInsights(BaseModel):
    """Description insights (optional section)."""

    description_summary: str | None = None
    key_requirements: list[str] = Field(default_factory=list)
    key_responsibilities_preview: str | None = None


class JobApplicationTracking(BaseModel):
    """Application tracking (optional section)."""

    application_status: str | None = None
    applied_at: str | None = None
    application_notes: str | None = None


class JobCompanyEnrichment(BaseModel):
    """Company enrichment (optional section)."""

    company_size: str | None = None
    company_industry: str | None = None
    company_description: str | None = None
    company_website: str | None = None
    company_headquarters: str | None = None
    company_founded: int | None = None
    company_specialties: list[str] = Field(default_factory=list)


class JobMetadata(BaseModel):
    """Metadata (optional section)."""

    job_url: str | None = None
    scraped_at: str | None = None
    last_seen: str | None = None
    seniority_level: str | None = None
    employment_type: str | None = None


class JobFullDescription(BaseModel):
    """Full description (optional section)."""

    description: str | None = None


class JobCompleteSkills(BaseModel):
    """Complete skills list (optional section)."""

    skills_required: list[str] = Field(default_factory=list)
    skills_preferred: list[str] = Field(default_factory=list)


class JobBenefits(BaseModel):
    """Benefits (optional section)."""

    benefits: list[str] = Field(default_factory=list)


class JobEmploymentDetails(BaseModel):
    """Employment details (optional section)."""

    workplace_type: str | None = None
    experience_level: str | None = None
    industry: str | None = None


class JobResponse(BaseModel):
    """Composable job response with optional sections.

    Core and decision_making sections are always included.
    Optional sections can be included based on include_* flags.
    """

    core: JobCore
    decision_making: JobDecisionMaking
    description_insights: JobDescriptionInsights | None = None
    application_tracking: JobApplicationTracking | None = None
    company_enrichment: JobCompanyEnrichment | None = None
    metadata: JobMetadata | None = None
    full_description: JobFullDescription | None = None
    complete_skills: JobCompleteSkills | None = None
    benefits: JobBenefits | None = None
    employment_details: JobEmploymentDetails | None = None
