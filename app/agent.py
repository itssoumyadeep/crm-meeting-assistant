# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
AI CRM Copilot - Multi-Agent Analysis Pipeline

Architecture:
  ParallelAgent runs 5 specialist agents concurrently:
    1. SummaryAgent          -> output_key="summary"
    2. ActionItemsAgent      -> output_key="action_items"
    3. BuyingSignalsAgent    -> output_key="buying_signals"
    4. CompetitorAgent       -> output_key="competitor_mentions"
    5. SentimentCrmAgent     -> output_key="sentiment_crm"

  Then OrchestratorAgent consolidates all outputs into the
  canonical JSON payload the frontend expects.
"""

from google.adk.agents import Agent, ParallelAgent, SequentialAgent
from google.adk.apps import App
from google.adk.models import Gemini
from google.genai import types

# ---------------------------------------------------------------------------
# Model shorthand
# ---------------------------------------------------------------------------
_MODEL = Gemini(
    model="gemini-flash-latest",
    retry_options=types.HttpRetryOptions(attempts=3),
)

# ---------------------------------------------------------------------------
# 1. Summary Agent
# ---------------------------------------------------------------------------
summary_agent = Agent(
    name="summary_agent",
    model=_MODEL,
    description="Produces a concise executive summary of a sales meeting transcript.",
    instruction="""
You are a senior sales analyst. Read the meeting transcript stored in
{transcript} and write a crisp executive summary (3-5 sentences) that covers:
- Who attended and what the meeting was about
- Key pain points the prospect raised
- Main themes discussed

Return ONLY raw JSON (no markdown fences) with this exact schema:
{
  "summary": "<your 3-5 sentence summary>",
  "evidence": "<1-2 verbatim quotes from the transcript that best support the summary>"
}
""",
    output_key="summary_result",
)

# ---------------------------------------------------------------------------
# 2. Action Items Agent
# ---------------------------------------------------------------------------
action_items_agent = Agent(
    name="action_items_agent",
    model=_MODEL,
    description="Extracts concrete follow-up action items from a sales meeting transcript.",
    instruction="""
You are an expert meeting scribe. Read the meeting transcript in {transcript}
and extract every concrete action item, commitment, or next step mentioned.

Return ONLY raw JSON (no markdown fences) with this exact schema:
{
  "action_items": [
    {
      "item": "<description of the action>",
      "owner": "<person responsible, or 'Unknown'>",
      "due": "<deadline or 'TBD'>",
      "evidence": "<verbatim quote from the transcript>"
    }
  ]
}

If no action items were found, return {"action_items": []}.
""",
    output_key="action_items_result",
)

# ---------------------------------------------------------------------------
# 3. Buying Signals Agent
# ---------------------------------------------------------------------------
buying_signals_agent = Agent(
    name="buying_signals_agent",
    model=_MODEL,
    description="Identifies positive and negative buying signals in a sales transcript.",
    instruction="""
You are a sales intelligence analyst. Read the meeting transcript in {transcript}
and identify buying signals — both positive (intent to buy, urgency, budget discussion,
decision-maker engagement) and negative (objections, competing priorities, budget freeze).

Return ONLY raw JSON (no markdown fences) with this schema:
{
  "buying_signals": [
    {
      "signal": "<description of the signal>",
      "polarity": "positive" | "negative",
      "strength": "strong" | "moderate" | "weak",
      "evidence": "<verbatim quote>"
    }
  ]
}

If no buying signals found, return {"buying_signals": []}.
""",
    output_key="buying_signals_result",
)

# ---------------------------------------------------------------------------
# 4. Competitor Mentions Agent
# ---------------------------------------------------------------------------
competitor_agent = Agent(
    name="competitor_agent",
    model=_MODEL,
    description="Detects competitor mentions and associated sentiment in a sales transcript.",
    instruction="""
You are a competitive intelligence specialist. Read the meeting transcript in {transcript}
and find every mention of a competitor, competing product, or alternative solution.
For each mention, note the context and sentiment.

Return ONLY raw JSON (no markdown fences) with this schema:
{
  "competitor_mentions": [
    {
      "competitor": "<name of competitor or product>",
      "context": "<what was said about them>",
      "sentiment": "favorable" | "unfavorable" | "neutral",
      "evidence": "<verbatim quote>"
    }
  ]
}

If no competitors mentioned, return {"competitor_mentions": []}.
""",
    output_key="competitor_mentions_result",
)

# ---------------------------------------------------------------------------
# 5. Sentiment & CRM Stage Agent
# ---------------------------------------------------------------------------
sentiment_crm_agent = Agent(
    name="sentiment_crm_agent",
    model=_MODEL,
    description="Assesses overall call sentiment and recommends a CRM pipeline stage.",
    instruction="""
You are a sales operations expert. Read the meeting transcript in {transcript}.

First, assess the overall sentiment of the prospect:
  - "very_positive", "positive", "neutral", "negative", "very_negative"

Then, recommend the most appropriate CRM pipeline stage:
  - "Lead", "Qualified", "Discovery", "Proposal", "Negotiation", "Closed Won", "Closed Lost"

Return ONLY raw JSON (no markdown fences) with this schema:
{
  "sentiment": {
    "overall": "<sentiment label>",
    "score": <number from -1.0 to 1.0>,
    "reasoning": "<1-2 sentence explanation>",
    "evidence": "<verbatim quote supporting sentiment>"
  },
  "crm_stage": {
    "recommended": "<stage name>",
    "confidence": "high" | "medium" | "low",
    "reasoning": "<1-2 sentence explanation>",
    "evidence": "<verbatim quote supporting stage recommendation>"
  }
}
""",
    output_key="sentiment_crm_result",
)

# ---------------------------------------------------------------------------
# Parallel Analysis Layer
# ---------------------------------------------------------------------------
analysis_pipeline = ParallelAgent(
    name="analysis_pipeline",
    description="Runs all specialist analysis agents concurrently on the transcript.",
    sub_agents=[
        summary_agent,
        action_items_agent,
        buying_signals_agent,
        competitor_agent,
        sentiment_crm_agent,
    ],
)

# ---------------------------------------------------------------------------
# Orchestrator Agent (consolidates parallel outputs)
# ---------------------------------------------------------------------------
orchestrator_agent = Agent(
    name="orchestrator_agent",
    model=_MODEL,
    description="Consolidates all specialist analysis results into a single structured JSON payload.",
    instruction="""
You are the final consolidation agent. All specialist agents have already run and
stored their results in session state. Your job is to merge them into one clean payload.

Available results (already parsed JSON strings in session state):
- summary_result: {summary_result}
- action_items_result: {action_items_result}
- buying_signals_result: {buying_signals_result}
- competitor_mentions_result: {competitor_mentions_result}
- sentiment_crm_result: {sentiment_crm_result}

Parse each JSON string and merge into ONE JSON object with this exact top-level schema:
{
  "summary": { ...from summary_result... },
  "action_items": [ ...from action_items_result... ],
  "buying_signals": [ ...from buying_signals_result... ],
  "competitor_mentions": [ ...from competitor_mentions_result... ],
  "sentiment": { ...from sentiment_crm_result.sentiment... },
  "crm_stage": { ...from sentiment_crm_result.crm_stage... }
}

Return ONLY the raw merged JSON object. No markdown fences, no explanation.
If a specialist result looks like already-parsed JSON embedded in a string,
extract it properly. Preserve all fields including all "evidence" fields.
""",
    output_key="analysis_result",
)

# ---------------------------------------------------------------------------
# Root SequentialAgent: first parallel analysis, then consolidation
# ---------------------------------------------------------------------------
root_agent = SequentialAgent(
    name="crm_copilot_pipeline",
    description="AI CRM Copilot: analyses meeting transcripts with a multi-agent pipeline.",
    sub_agents=[analysis_pipeline, orchestrator_agent],
)

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = App(
    root_agent=root_agent,
    name="app",
)
