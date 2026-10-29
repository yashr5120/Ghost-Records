"""Pydantic schemas for validating structured AI outputs."""


from pydantic import BaseModel, Field


class FindingExplanationSchema(BaseModel):
    """Structured response schema for evidence-grounded AI explanations."""

    summary: str = Field(
        ...,
        description="A concise 1-2 sentence forensic summary of the detected anomaly.",
    )
    why_flagged: str = Field(
        ...,
        description="Clear explanation of the exact rule or constraint violation observed in the evidence.",
    )
    likely_explanations: list[str] = Field(
        default_factory=list,
        description="2-4 plausible technical or operational reasons why this data condition occurred.",
    )
    verification_steps: list[str] = Field(
        default_factory=list,
        description="Step-by-step human verification instructions to check before modifying data.",
    )
    recommended_remediation: str = Field(
        ...,
        description="Safe, non-destructive recommended action (e.g. quarantine, review, deduplicate in copy).",
    )
    confidence_statement: str = Field(
        ...,
        description="Explicit statement of certainty or uncertainty based strictly on supplied evidence.",
    )
