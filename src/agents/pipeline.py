from google.adk.agents import Agent, SequentialAgent
from google.adk.models import Gemini
from google.genai import types
from src.agents.schemas import TranscriptSummary, Signals, CRMRecommendation

# Initialize the Gemini model matching project settings
model = Gemini(
    model="gemini-flash-latest",
    retry_options=types.HttpRetryOptions(attempts=3),
)

# 1. Transcript Agent
# Focuses on summarizing the meeting, extracting action items, and follow-up tasks.
transcript_agent = Agent(
    name="transcript_agent",
    model=model,
    description="Summarizes meeting transcripts, extracts action items and follow-up tasks.",
    instruction="""
    Analyze the meeting transcript in {transcript}.
    Produce a concise executive summary of the meeting, list all concrete action items, 
    and identify any follow-up tasks.
    """,
    output_schema=TranscriptSummary,
    output_key="transcript_summary",
)

# 2. Signal Agent
# Detects buying signals, competitor mentions, and customer sentiment.
signal_agent = Agent(
    name="signal_agent",
    model=model,
    description="Detects buying signals, competitor mentions, and customer sentiment.",
    instruction="""
    Review the original meeting transcript:
    {transcript}
    
    And the transcript analysis summary:
    {transcript_summary}
    
    Identify:
    - Buying signals (positive or negative indicators of interest, budget, timeline, authority).
    - Competitor mentions (any products, services, or companies competing with us).
    - Overall customer sentiment (e.g., Positive, Neutral, Negative, Mixed) along with a brief explanation.
    """,
    output_schema=Signals,
    output_key="signals",
)

# 3. CRM Mapper Agent
# Recommends CRM stages and recommends CRM field updates.
crm_mapper_agent = Agent(
    name="crm_mapper_agent",
    model=model,
    description="Recommends appropriate CRM stage and CRM field updates based on analyzed meetings.",
    instruction="""
    Based on the meeting summary:
    {transcript_summary}
    
    And the detected signals:
    {signals}
    
    Recommend:
    - The most appropriate CRM stage (e.g., Prospecting, Qualified, Proposal, Negotiation, Closed Won, Closed Lost).
    - Proposed updates to key fields (e.g., deal amount/value, closing date estimation, company, title).
    """,
    output_schema=CRMRecommendation,
    output_key="crm_recommendation",
)

# Root Sequential Agent chaining the pipeline
pipeline = SequentialAgent(
    name="crm_sequential_pipeline",
    description="CRM Meeting Assistant Sequential Multi-Agent Pipeline",
    sub_agents=[
        transcript_agent,
        signal_agent,
        crm_mapper_agent,
    ],
)
