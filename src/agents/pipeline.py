import os
import re
from google.adk.agents import Agent, SequentialAgent
from google.adk.models import Gemini
from google.adk.tools import BaseTool, ToolContext
from google.genai import types
from src.agents.schemas import TranscriptSummary, Signals, CRMRecommendation
from src.mcp_server.server import get_deal_stage_options

# Initialize the Gemini model matching project settings
model = Gemini(
    model="gemini-flash-latest",
    retry_options=types.HttpRetryOptions(attempts=3),
)

# ---------------------------------------------------------------------------
# Load playbooks and skills
# ---------------------------------------------------------------------------
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PLAYBOOK_PATH = os.path.join(BASE_DIR, "src", "skills", "deal-scoring-skill", "playbook.md")

with open(PLAYBOOK_PATH, "r", encoding="utf-8") as f:
    playbook_content = f.read()

# ---------------------------------------------------------------------------
# Tool definition
# ---------------------------------------------------------------------------
def propose_crm_update(recommended_stage: str, recommended_field_updates: dict) -> dict:
    """
    Propose an update to the CRM deal stage and fields.
    
    Args:
        recommended_stage: The recommended target stage.
        recommended_field_updates: Key-value updates for fields.
    """
    return {
        "status": "success",
        "recommended_stage": recommended_stage,
        "recommended_field_updates": recommended_field_updates,
    }

# ---------------------------------------------------------------------------
# Callbacks and Guardrails
# ---------------------------------------------------------------------------
# Regex to redact credit cards and Social Insurance Numbers / SSN
CC_REGEX = re.compile(r"\b(?:\d[ -]*?){13,16}\b")
SSN_REGEX = re.compile(r"\b\d{3}-\d{2}-\d{4}\b|\b\d{3} \d{3} \d{3}\b|\b\d{9}\b")

# Dangerous prompt injection patterns
INJECTION_PHRASES = [
    "ignore previous instructions",
    "system prompt",
    "disregard",
    "as an ai",
]

def redact_sensitive_info(val: str) -> str:
    if not isinstance(val, str):
        return val
    val = CC_REGEX.sub("[REDACTED CREDIT CARD]", val)
    val = SSN_REGEX.sub("[REDACTED SSN/SIN]", val)
    return val

async def before_tool_callback(tool: BaseTool, args: dict, tool_context: ToolContext) -> dict | None:
    # 1. Prevent execution of any tool except propose_crm_update()
    if tool.name != "propose_crm_update":
        raise ValueError(f"Tool execution blocked: Only 'propose_crm_update' is permitted. Attempted: '{tool.name}'")

    # 2. Block prompt injection phrases in inputs
    for key, value in args.items():
        if isinstance(value, str):
            val_lower = value.lower()
            for phrase in INJECTION_PHRASES:
                if phrase in val_lower:
                    raise ValueError(f"Execution blocked: Potential prompt injection detected in argument '{key}' containing phrase '{phrase}'")

    # 3. Validate CRM stage using get_deal_stage_options()
    stage = args.get("recommended_stage")
    if stage:
        valid_stages = get_deal_stage_options()
        if stage not in valid_stages:
            raise ValueError(f"Invalid CRM stage proposed: '{stage}'. Permitted stages: {valid_stages}")

    # 4. Redact credit cards and SIN/SSN from string parameters
    for key, value in args.items():
        if isinstance(value, str):
            args[key] = redact_sensitive_info(value)
        elif isinstance(value, dict):
            for sub_key, sub_val in value.items():
                if isinstance(sub_val, str):
                    value[sub_key] = redact_sensitive_info(sub_val)

    return None

# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------
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

crm_mapper_agent = Agent(
    name="crm_mapper_agent",
    model=model,
    description="Recommends appropriate CRM stage and CRM field updates based on analyzed meetings.",
    instruction=f"""
    Based on the meeting summary:
    {{transcript_summary}}
    
    And the detected signals:
    {{signals}}
    
    Recommend:
    - The most appropriate CRM stage.
    - Proposed updates to key fields (e.g., deal amount/value, closing date estimation, company, title).
    
    Refer to the deal scoring methodology defined in the playbook below:
    {playbook_content}
    """,
    output_schema=CRMRecommendation,
    output_key="crm_recommendation",
    tools=[propose_crm_update],
    before_tool_callback=before_tool_callback,
)

pipeline = SequentialAgent(
    name="crm_sequential_pipeline",
    description="CRM Meeting Assistant Sequential Multi-Agent Pipeline",
    sub_agents=[
        transcript_agent,
        signal_agent,
        crm_mapper_agent,
    ],
)
