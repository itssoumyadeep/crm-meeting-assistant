"""
Streamlit UI for the CRM Meeting Assistant.

Eight tabs guide the user through the full workflow:

  1. Paste Transcript    — load or type a meeting transcript
  2. Run Analysis        — invoke the ADK multi-agent pipeline
  3. Summary             — executive summary, action items, follow-ups
  4. Buying Signals      — positive and negative buying indicators
  5. Sentiment           — overall customer sentiment
  6. Competitor Mentions — competitors referenced during the call
  7. Proposed Updates    — review, edit, approve, or reject AI suggestions
  8. Activity History    — full audit trail of approved/rejected updates

Design notes:
- All database and service objects are constructed once per Python process
  (outside the render loop) and cached via @st.cache_resource so Streamlit's
  hot-reload does not create multiple connections.
- asyncio.run() is used to bridge Streamlit's synchronous execution model with
  the async ADK runner.  This works because Streamlit runs each user interaction
  in a fresh thread with no pre-existing event loop.
"""
import asyncio
import json
import logging
import os

import streamlit as st
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from src.agents.pipeline import pipeline
from src.database.db_helper import DatabaseHelper
from src.services.crm_service import CRMService
from src.utils.config import ADK_APP_NAME, DB_PATH, SAMPLE_TRANSCRIPTS_DIR
from src.utils.logging_config import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Page config (must be the first Streamlit call)
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="CRM Meeting Assistant",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Custom CSS — premium dark theme
# ---------------------------------------------------------------------------
st.markdown(
    """
<style>
    .main { background-color: #0f172a; color: #f8fafc; }
    .stTabs [data-baseweb="tab-list"] { gap: 12px; }
    .stTabs [data-baseweb="tab"] {
        background-color: #1e293b;
        border-radius: 8px;
        color: #94a3b8;
        padding: 10px 20px;
        transition: all 0.3s ease;
    }
    .stTabs [data-baseweb="tab"]:hover { color: #f8fafc; background-color: #334155; }
    .stTabs [aria-selected="true"] {
        background-color: #2563eb !important;
        color: #ffffff !important;
        font-weight: bold;
    }
    .metric-card {
        background-color: #1e293b;
        border: 1px solid #334155;
        border-radius: 12px;
        padding: 20px;
        margin-bottom: 15px;
    }
    .evidence-box {
        background-color: #0f172a;
        border-left: 4px solid #3b82f6;
        padding: 12px;
        border-radius: 4px;
        margin-top: 8px;
        font-style: italic;
    }
</style>
""",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Cached singletons — created once per process, not per page rerun
# ---------------------------------------------------------------------------

@st.cache_resource
def _get_db() -> DatabaseHelper:
    return DatabaseHelper(DB_PATH)


@st.cache_resource
def _get_crm_service() -> CRMService:
    return CRMService(_get_db())


db: DatabaseHelper = _get_db()
crm_service: CRMService = _get_crm_service()

# ---------------------------------------------------------------------------
# Session-state initialisation
# ---------------------------------------------------------------------------
_SESSION_DEFAULTS: dict = {
    "analysis_complete": False,
    "transcript_text": "",
    "summary": None,
    "signals": None,
    "crm_recommendation": None,
}
for _key, _default in _SESSION_DEFAULTS.items():
    if _key not in st.session_state:
        st.session_state[_key] = _default

# ---------------------------------------------------------------------------
# ADK pipeline runner
# ---------------------------------------------------------------------------

async def _run_pipeline_async(transcript_content: str) -> dict:
    """
    Execute the CRM multi-agent pipeline against *transcript_content*.

    Creates a fresh in-memory ADK session, injects the transcript into
    session state, runs the pipeline to completion, and returns the three
    output keys written by the sub-agents.

    Args:
        transcript_content: Raw meeting transcript text.

    Returns:
        Dict with keys ``transcript_summary``, ``signals``, ``crm_recommendation``.

    Raises:
        RuntimeError: Wrapped around any ADK runner exception.
    """
    session_service = InMemorySessionService()
    await session_service.create_session(
        app_name=ADK_APP_NAME, user_id="user", session_id="s1"
    )

    # Inject the transcript before the pipeline starts
    session = await session_service.get_session("s1")
    session.state["transcript"] = transcript_content

    runner = Runner(
        agent=pipeline, app_name=ADK_APP_NAME, session_service=session_service
    )

    logger.info("Starting pipeline run for transcript (%d chars).", len(transcript_content))
    async for _ in runner.run_async(
        user_id="user",
        session_id="s1",
        new_message=types.Content(
            role="user", parts=[types.Part.from_text(text="Analyse this meeting transcript.")]
        ),
    ):
        pass  # drain the event stream; outputs land in session.state

    logger.info("Pipeline run complete.")
    return {
        "transcript_summary": session.state.get("transcript_summary"),
        "signals": session.state.get("signals"),
        "crm_recommendation": session.state.get("crm_recommendation"),
    }

# ---------------------------------------------------------------------------
# Helper — "not yet run" notice
# ---------------------------------------------------------------------------

def _analysis_required_notice() -> None:
    st.info("Analysis has not been run yet. Go to **Tab 2 – Run Analysis** first.")

# ---------------------------------------------------------------------------
# Helper — load sample transcript file list
# ---------------------------------------------------------------------------

def _get_sample_files() -> list[str]:
    if SAMPLE_TRANSCRIPTS_DIR.exists():
        return sorted(f for f in os.listdir(SAMPLE_TRANSCRIPTS_DIR) if f.endswith(".txt"))
    return []

# ---------------------------------------------------------------------------
# Page header
# ---------------------------------------------------------------------------
st.title("💼 CRM Meeting Assistant")
st.subheader("AI-Driven Meeting Analysis and Pipeline Sync")

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------
tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs([
    "📝 1. Paste Transcript",
    "⚡ 2. Run Analysis",
    "📋 3. Summary",
    "📈 4. Buying Signals",
    "❤️ 5. Sentiment",
    "⚔️ 6. Competitor Mentions",
    "🔄 7. Proposed Updates",
    "📜 8. Activity History",
])

# ─── Tab 1: Paste Transcript ───────────────────────────────────────────────
with tab1:
    st.header("Paste Meeting Transcript")

    sample_files = _get_sample_files()
    selected_sample = st.selectbox(
        "Load a sample transcript (optional)",
        options=["None"] + sample_files,
    )

    # When a sample is chosen, overwrite the session text immediately
    if selected_sample != "None":
        sample_path = SAMPLE_TRANSCRIPTS_DIR / selected_sample
        st.session_state.transcript_text = sample_path.read_text(encoding="utf-8")

    st.write("Paste or type the meeting transcript below.")
    transcript_input = st.text_area(
        "Transcript",
        height=300,
        placeholder="Paste the meeting transcript here…",
        value=st.session_state.transcript_text,
    )
    # Sync manual edits back to session state
    if transcript_input != st.session_state.transcript_text:
        st.session_state.transcript_text = transcript_input

# ─── Tab 2: Run Analysis ───────────────────────────────────────────────────
with tab2:
    st.header("Run Multi-Agent Analysis")

    if not st.session_state.transcript_text:
        st.warning("Please paste or load a transcript in **Tab 1** first.")
    else:
        st.write("Click the button below to run the full analysis pipeline.")
        if st.button("▶ Start AI Analysis", type="primary"):
            with st.spinner("Running pipeline — this may take 30–60 seconds…"):
                try:
                    results = asyncio.run(
                        _run_pipeline_async(st.session_state.transcript_text)
                    )
                except Exception as exc:
                    logger.exception("Pipeline execution failed.")
                    st.error(f"Pipeline error: {exc}")
                    st.stop()

            st.session_state.summary = results["transcript_summary"]
            st.session_state.signals = results["signals"]
            st.session_state.crm_recommendation = results["crm_recommendation"]
            st.session_state.analysis_complete = True

            # Stage the AI recommendation for human review
            rec = results["crm_recommendation"]
            crm_service.create_pending_update(
                target_table="deals",
                target_id=1,  # Placeholder; real UI would resolve from context
                proposed_changes={
                    "stage": rec.recommended_stage,
                    "evidence": "Extracted from buying signals and stage alignment.",
                    "confidence_score": 0.85,
                    "details": rec.recommended_field_updates,
                },
                source_transcript_id=(
                    selected_sample if selected_sample != "None" else "custom_transcript"
                ),
            )

            st.success("Analysis complete! Use the tabs above to explore results.")

# ─── Tab 3: Summary ────────────────────────────────────────────────────────
with tab3:
    st.header("Meeting Summary")
    if not st.session_state.analysis_complete:
        _analysis_required_notice()
    else:
        summary = st.session_state.summary
        st.markdown(f"### Executive Summary\n\n{summary.summary}")

        col_actions, col_followups = st.columns(2)
        with col_actions:
            st.subheader("Action Items")
            for item in summary.action_items:
                st.write(f"- {item}")
        with col_followups:
            st.subheader("Follow-up Tasks")
            for task in summary.follow_up_tasks:
                st.write(f"- {task}")

# ─── Tab 4: Buying Signals ─────────────────────────────────────────────────
with tab4:
    st.header("Buying Signals")
    if not st.session_state.analysis_complete:
        _analysis_required_notice()
    else:
        signals = st.session_state.signals
        if not signals.buying_signals:
            st.info("No buying signals detected in this transcript.")
        else:
            for idx, signal in enumerate(signals.buying_signals, start=1):
                st.markdown(
                    f"<div class='metric-card'><h4>Signal #{idx}</h4><p>{signal}</p></div>",
                    unsafe_allow_html=True,
                )

# ─── Tab 5: Sentiment ──────────────────────────────────────────────────────
with tab5:
    st.header("Customer Sentiment")
    if not st.session_state.analysis_complete:
        _analysis_required_notice()
    else:
        st.info(st.session_state.signals.customer_sentiment)

# ─── Tab 6: Competitor Mentions ────────────────────────────────────────────
with tab6:
    st.header("Competitor Mentions")
    if not st.session_state.analysis_complete:
        _analysis_required_notice()
    else:
        mentions = st.session_state.signals.competitor_mentions
        if not mentions:
            st.success("No competitors mentioned in this call.")
        else:
            for mention in mentions:
                st.write(f"- {mention}")

# ─── Tab 7: Proposed CRM Updates ───────────────────────────────────────────
with tab7:
    st.header("Review Proposed CRM Updates")
    pending_list = crm_service.get_pending_updates()

    if not pending_list:
        st.success("No pending updates to review — inbox clear!")
    else:
        for update in pending_list:
            update_id: int = update["id"]
            changes: dict = json.loads(update["proposed_changes"])

            st.markdown(
                f"### Update #{update_id} — "
                f"`{update['target_table']}` record #{update['target_id']}"
            )

            col_meta, col_detail = st.columns(2)
            with col_meta:
                st.markdown(f"**Proposed Stage**: `{changes.get('stage', '—')}`")
                st.markdown(f"**Confidence**: `{changes.get('confidence_score', 'N/A')}`")
                st.markdown(f"**Source**: `{update.get('source_transcript_id', '—')}`")
            with col_detail:
                st.markdown("**Field Updates:**")
                st.json(changes.get("details", {}))

            st.markdown("**Transcript Evidence:**")
            st.markdown(
                f"<div class='evidence-box'>"
                f"{changes.get('evidence', 'No evidence specified.')}"
                f"</div>",
                unsafe_allow_html=True,
            )

            approver_name: str = st.text_input(
                "Your name (approver)",
                value="Sales Manager",
                key=f"approver_{update_id}",
            )

            st.markdown("#### Decision")
            col_approve, col_reject, col_edit = st.columns(3)

            with col_approve:
                if st.button(f"✅ Approve #{update_id}", key=f"approve_{update_id}"):
                    if crm_service.commit_crm_update(
                        update_id, overridden_changes=changes, approver=approver_name
                    ):
                        st.success(f"Update #{update_id} committed.")
                        st.rerun()

            with col_reject:
                if st.button(f"❌ Reject #{update_id}", key=f"reject_{update_id}"):
                    if crm_service.reject_crm_update(update_id, approver=approver_name):
                        st.warning(f"Update #{update_id} discarded.")
                        st.rerun()

            with col_edit:
                new_stage = st.text_input(
                    "Override stage",
                    value=changes.get("stage", ""),
                    key=f"stage_edit_{update_id}",
                )
                if st.button(f"💾 Save edit #{update_id}", key=f"save_edit_{update_id}"):
                    changes["stage"] = new_stage
                    db.execute(
                        "UPDATE pending_updates SET proposed_changes = ? WHERE id = ?",
                        (json.dumps(changes), update_id),
                    )
                    st.success(f"Stage for update #{update_id} overridden.")
                    st.rerun()

            st.divider()

# ─── Tab 8: Activity History ───────────────────────────────────────────────
with tab8:
    st.header("Activity History (Audit Trail)")
    audit_logs = db.fetch_all("SELECT * FROM audit_logs ORDER BY timestamp DESC")

    if not audit_logs:
        st.info("No audit entries recorded yet.")
    else:
        for log in audit_logs:
            details: dict = json.loads(log["change_details"])
            st.markdown(
                f"### Log #{log['id']} — `{log['action']}` on "
                f"`{log['target_table']}` #{log['target_id']}"
            )
            st.caption(f"Recorded at: {log['timestamp']}")

            col_ai, col_human = st.columns(2)
            with col_ai:
                st.markdown("**AI Suggestion:**")
                st.json(details.get("ai_suggestion"))
            with col_human:
                human_edits = details.get("human_edits")
                st.markdown("**Committed Changes (human edits):**")
                st.json(human_edits if human_edits else "— rejected, no changes applied —")

            st.markdown(
                f"**Approver:** `{details.get('approver', '—')}` | "
                f"**Outcome:** `{details.get('status', '—')}`"
            )
            st.divider()
