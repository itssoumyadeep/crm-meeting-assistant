"""
ADK multi-agent pipeline for the CRM Meeting Assistant.

Pipeline stages (executed in order by SequentialAgent):

1. TranscriptAgent  — summarise the meeting; extract action items & follow-ups.
2. SignalAgent      — detect buying signals, competitors, and customer sentiment.
3. CRMMapperAgent   — recommend CRM stage and field updates using the deal-scoring
                      playbook; protected by before_tool_callback guardrails.

State propagation:
    transcript          → provided by the caller before run_async
    transcript_summary  → written by TranscriptAgent; read by SignalAgent & CRMMapperAgent
    signals             → written by SignalAgent; read by CRMMapperAgent
    crm_recommendation  → written by CRMMapperAgent; read by the UI layer

Guardrails (before_tool_callback on CRMMapperAgent):
  - Blocks every tool except ``propose_crm_update``.
  - Rejects args containing prompt-injection phrases.
  - Validates the recommended CRM stage against the allow-list in config.
  - Redacts credit-card numbers and SIN/SSN patterns from string arguments.
"""
import re
from typing import Optional

from google.adk.agents import Agent, SequentialAgent
from google.adk.models import Gemini
from google.adk.tools import BaseTool, ToolContext
from google.genai import types

from src.agents.schemas import CRMRecommendation, Signals, TranscriptSummary
from src.mcp_server.server import get_deal_stage_options
from src.utils.config import (
    ALLOWED_TOOL_NAME,
    INJECTION_PHRASES,
    MODEL_NAME,
    MODEL_RETRY_ATTEMPTS,
    PLAYBOOK_PATH,
)
from src.utils.logging_config import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Model — shared across all three agents
# ---------------------------------------------------------------------------
_model = Gemini(
    model=MODEL_NAME,
    retry_options=types.HttpRetryOptions(attempts=MODEL_RETRY_ATTEMPTS),
)

# ---------------------------------------------------------------------------
# Load deal-scoring playbook (injected into CRMMapperAgent's instruction)
# ---------------------------------------------------------------------------
if not PLAYBOOK_PATH.exists():
    raise FileNotFoundError(f"Deal-scoring playbook not found: {PLAYBOOK_PATH}")

_playbook_content: str = PLAYBOOK_PATH.read_text(encoding="utf-8")
logger.info("Loaded deal-scoring playbook from %s", PLAYBOOK_PATH)

# ---------------------------------------------------------------------------
# PII redaction — compiled once at module load
# ---------------------------------------------------------------------------
_CC_REGEX = re.compile(r"\b(?:\d[ -]*?){13,16}\b")
_SSN_REGEX = re.compile(r"\b\d{3}-\d{2}-\d{4}\b|\b\d{3} \d{3} \d{3}\b|\b\d{9}\b")


def _redact_sensitive_info(value: str) -> str:
    """Replace credit-card and SIN/SSN patterns with placeholder tokens."""
    value = _CC_REGEX.sub("[REDACTED CREDIT CARD]", value)
    value = _SSN_REGEX.sub("[REDACTED SSN/SIN]", value)
    return value


def _redact_args(args: dict) -> None:
    """Redact PII from all string values in *args*, mutating the dict in place."""
    for key, value in args.items():
        if isinstance(value, str):
            args[key] = _redact_sensitive_info(value)
        elif isinstance(value, dict):
            for sub_key, sub_val in value.items():
                if isinstance(sub_val, str):
                    value[sub_key] = _redact_sensitive_info(sub_val)

# ---------------------------------------------------------------------------
# Tool definition — the only tool CRMMapperAgent is allowed to call
# ---------------------------------------------------------------------------

def propose_crm_update(recommended_stage: str, recommended_field_updates: dict) -> dict:
    """
    Propose a CRM stage change and field updates for human review.

    This function intentionally performs no database writes — it simply echoes
    the proposed values back so the guardrail layer can inspect them and the
    result can be stored as a pending_update record by the UI service layer.

    Args:
        recommended_stage:        Target pipeline stage name.
        recommended_field_updates: Key/value pairs for deal fields to update.

    Returns:
        Dict with ``status``, ``recommended_stage``, and ``recommended_field_updates``.
    """
    return {
        "status": "success",
        "recommended_stage": recommended_stage,
        "recommended_field_updates": recommended_field_updates,
    }

# ---------------------------------------------------------------------------
# Guardrail callback
# ---------------------------------------------------------------------------

async def before_tool_callback(
    tool: BaseTool, args: dict, tool_context: ToolContext
) -> Optional[dict]:
    """
    Pre-flight safety checks executed before every tool call on CRMMapperAgent.

    Checks (in order):
    1. Block every tool except ``propose_crm_update``.
    2. Reject any string argument containing a known prompt-injection phrase.
    3. Validate ``recommended_stage`` against the canonical allow-list.
    4. Redact credit-card numbers and SIN/SSN patterns from string args.

    Returns:
        ``None`` to let the tool proceed, or raises ``ValueError`` to block it.
    """
    # 1. Tool allow-list
    if tool.name != ALLOWED_TOOL_NAME:
        msg = f"Blocked tool '{tool.name}': only '{ALLOWED_TOOL_NAME}' is permitted."
        logger.warning(msg)
        raise ValueError(msg)

    # 2. Prompt-injection detection
    for arg_name, arg_value in args.items():
        if isinstance(arg_value, str):
            lower_val = arg_value.lower()
            for phrase in INJECTION_PHRASES:
                if phrase in lower_val:
                    msg = (
                        f"Blocked: prompt-injection phrase '{phrase}' "
                        f"detected in argument '{arg_name}'."
                    )
                    logger.warning(msg)
                    raise ValueError(msg)

    # 3. CRM stage allow-list validation
    proposed_stage: Optional[str] = args.get("recommended_stage")
    if proposed_stage is not None:
        valid_stages = get_deal_stage_options()
        if proposed_stage not in valid_stages:
            msg = (
                f"Blocked: invalid CRM stage '{proposed_stage}'. "
                f"Valid options: {valid_stages}"
            )
            logger.warning(msg)
            raise ValueError(msg)

    # 4. PII redaction (mutates args in-place)
    _redact_args(args)

    logger.debug("before_tool_callback: '%s' passed all checks.", tool.name)
    return None

# ---------------------------------------------------------------------------
# Agent definitions
# ---------------------------------------------------------------------------

transcript_agent = Agent(
    name="transcript_agent",
    model=_model,
    description="Summarises meeting transcripts and extracts action items and follow-up tasks.",
    instruction="""
    Carefully analyse the meeting transcript provided in {transcript}.

    Produce:
    - A concise executive summary (3–5 sentences) covering attendees, key pain points, and main themes.
    - A complete list of concrete action items or commitments made during the call.
    - A list of follow-up tasks that need to happen after the meeting.
    """,
    output_schema=TranscriptSummary,
    output_key="transcript_summary",
)

signal_agent = Agent(
    name="signal_agent",
    model=_model,
    description="Detects buying signals, competitor mentions, and overall customer sentiment.",
    instruction="""
    Review the following meeting transcript:
    {transcript}

    And its analysis summary:
    {transcript_summary}

    Identify:
    - Buying signals — both positive (budget confirmed, executive sponsor, tight timeline) and
      negative (frozen budget, competing priorities, vague commitment).
    - Competitor mentions — any competitor name, product, or alternative solution referenced.
    - Overall customer sentiment — one of: Positive, Neutral, Negative, Mixed — plus a
      one-sentence justification grounded in the transcript.
    """,
    output_schema=Signals,
    output_key="signals",
)

crm_mapper_agent = Agent(
    name="crm_mapper_agent",
    model=_model,
    description=(
        "Maps meeting analysis to a recommended CRM stage and field updates, "
        "guided by the deal-scoring playbook."
    ),
    instruction=f"""
    Based on the meeting summary:
    {{transcript_summary}}

    And the detected signals:
    {{signals}}

    Using the deal-scoring methodology below, recommend:
    1. The most appropriate CRM pipeline stage.
    2. Specific CRM field updates (e.g. deal amount, expected close date, company, job title).

    Deal-scoring playbook:
    {_playbook_content}
    """,
    output_schema=CRMRecommendation,
    output_key="crm_recommendation",
    tools=[propose_crm_update],
    before_tool_callback=before_tool_callback,
)

# ---------------------------------------------------------------------------
# Root sequential pipeline
# ---------------------------------------------------------------------------

pipeline = SequentialAgent(
    name="crm_meeting_pipeline",
    description=(
        "Sequential multi-agent pipeline: analyses a meeting transcript and "
        "produces structured CRM recommendations."
    ),
    sub_agents=[
        transcript_agent,
        signal_agent,
        crm_mapper_agent,
    ],
)
