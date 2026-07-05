from pydantic import BaseModel, Field
from typing import List, Dict, Any

class TranscriptSummary(BaseModel):
    summary: str = Field(description="A concise executive summary of the sales meeting (3-5 sentences).")
    action_items: List[str] = Field(description="List of action items extracted from the meeting.")
    follow_up_tasks: List[str] = Field(description="List of follow-up tasks identified from the meeting.")

class Signals(BaseModel):
    buying_signals: List[str] = Field(description="List of detected buying signals from the customer.")
    competitor_mentions: List[str] = Field(description="List of competitor names or products mentioned.")
    customer_sentiment: str = Field(description="Customer sentiment (e.g., Positive, Neutral, Negative, Mixed) with brief justification.")

class CRMRecommendation(BaseModel):
    recommended_stage: str = Field(description="Recommended CRM stage transition (e.g., Prospecting, Qualified, Proposal, Negotiation, Closed Won, Closed Lost).")
    recommended_field_updates: Dict[str, Any] = Field(description="Proposed updates to CRM fields (e.g., amount, close_date, company, job_title) based on meeting details.")
