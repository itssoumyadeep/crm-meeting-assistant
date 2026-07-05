"""
Pydantic schemas defining the structured JSON contract between agents in the
CRM Meeting Assistant pipeline.

Each schema is used as an ``output_schema`` on an ADK Agent, which instructs
the LLM to return valid JSON matching the model and stores the parsed object
at the key specified by ``output_key``.

Warning: ADK's structured-output mode (output_schema) disables tool-calling
for that agent, so none of these agents may also use tools.
"""
from pydantic import BaseModel, Field


class TranscriptSummary(BaseModel):
    """Output contract for TranscriptAgent."""

    summary: str = Field(
        description="Concise executive summary of the sales meeting (3–5 sentences)."
    )
    action_items: list[str] = Field(
        description="Concrete action items extracted from the meeting."
    )
    follow_up_tasks: list[str] = Field(
        description="Follow-up tasks identified from the meeting discussion."
    )


class Signals(BaseModel):
    """Output contract for SignalAgent."""

    buying_signals: list[str] = Field(
        description="Detected buying signals (positive or negative indicators of intent)."
    )
    competitor_mentions: list[str] = Field(
        description="Competitor names or products mentioned during the call."
    )
    customer_sentiment: str = Field(
        description=(
            "Overall customer sentiment — one of: Positive, Neutral, Negative, Mixed "
            "— followed by a brief one-sentence justification."
        )
    )


class CRMRecommendation(BaseModel):
    """Output contract for CRMMapperAgent."""

    recommended_stage: str = Field(
        description=(
            "Most appropriate CRM pipeline stage. Must be one of: "
            "Prospecting, Qualified, Proposal, Negotiation, Closed Won, Closed Lost."
        )
    )
    recommended_field_updates: dict[str, object] = Field(
        description=(
            "Proposed updates for CRM deal fields (e.g., amount, close_date, "
            "company, job_title) inferred from the meeting."
        )
    )
