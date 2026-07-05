import streamlit as st
import asyncio
import os
import json
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from src.database.db_helper import DatabaseHelper
from src.services.crm_service import CRMService
from src.agents.pipeline import pipeline

# Configure Page Layout and Aesthetics
st.set_page_config(
    page_title="CRM Meeting Assistant",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Premium design custom styles
st.markdown("""
<style>
    .main {
        background-color: #0f172a;
        color: #f8fafc;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 12px;
    }
    .stTabs [data-baseweb="tab"] {
        background-color: #1e293b;
        border-radius: 8px;
        color: #94a3b8;
        padding: 10px 20px;
        transition: all 0.3s ease;
    }
    .stTabs [data-baseweb="tab"]:hover {
        color: #f8fafc;
        background-color: #334155;
    }
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
""", unsafe_allow_html=True)

# Database and Service Initialization
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DB_PATH = os.path.join(BASE_DIR, "crm_assistant.db")
db = DatabaseHelper(DB_PATH)
crm_service = CRMService(db)

# Session State for storing analysis results
if "analysis_complete" not in st.session_state:
    st.session_state.analysis_complete = False
if "transcript_text" not in st.session_state:
    st.session_state.transcript_text = ""
if "summary" not in st.session_state:
    st.session_state.summary = {}
if "signals" not in st.session_state:
    st.session_state.signals = {}
if "crm_recommendation" not in st.session_state:
    st.session_state.crm_recommendation = {}

# ---------------------------------------------------------------------------
# Runner Execution Helper
# ---------------------------------------------------------------------------
async def run_pipeline_async(transcript_content: str):
    session_service = InMemorySessionService()
    await session_service.create_session(app_name="crm_assistant", user_id="user", session_id="s1")
    
    # Pre-populate session state with the transcript
    session = await session_service.get_session("s1")
    session.state["transcript"] = transcript_content
    
    runner = Runner(agent=pipeline, app_name="crm_assistant", session_service=session_service)
    
    async for event in runner.run_async(
        user_id="user",
        session_id="s1",
        new_message=types.Content(role="user", parts=[types.Part.from_text(text="Analyze transcript.")]),
    ):
        pass  # Running through to completion
        
    return {
        "transcript_summary": session.state.get("transcript_summary"),
        "signals": session.state.get("signals"),
        "crm_recommendation": session.state.get("crm_recommendation"),
    }

# Title header
st.title("💼 CRM Meeting Assistant")
st.subheader("AI-Driven Meeting Analysis and Pipeline Sync")

# Tabs representing the 7 Pages / steps
tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    "📝 1. Paste Transcript",
    "⚡ 2. Run Analysis",
    "📋 3. Summary",
    "📈 4. Buying Signals",
    "❤️ 5. Sentiment",
    "⚔️ 6. Competitor Mentions",
    "🔄 7. Proposed Updates"
])

# Page 1: Paste Transcript
with tab1:
    st.header("Paste Meeting Transcript")
    st.write("Input the conversation transcript of your customer call to extract sales details.")
    transcript_input = st.text_area(
        "Transcript Text",
        height=300,
        placeholder="Paste transcript here...",
        value=st.session_state.transcript_text
    )
    if transcript_input:
        st.session_state.transcript_text = transcript_input

# Page 2: Run Analysis
with tab2:
    st.header("Analyze Transcript")
    if not st.session_state.transcript_text:
        st.warning("Please paste a transcript in Tab 1 first.")
    else:
        st.write("Ready to execute multi-agent analysis on your transcript.")
        if st.button("Start AI Analysis", type="primary"):
            with st.spinner("Executing sequential analysis pipeline..."):
                results = asyncio.run(run_pipeline_async(st.session_state.transcript_text))
                
                # Store in session state
                st.session_state.summary = results["transcript_summary"]
                st.session_state.signals = results["signals"]
                st.session_state.crm_recommendation = results["crm_recommendation"]
                st.session_state.analysis_complete = True
                
                # Insert a pending update into SQLite to review in Tab 7
                crm_service.create_pending_update(
                    target_table="deals",
                    target_id=1,  # Default deal ID for testing
                    proposed_changes={
                        "stage": results["crm_recommendation"].recommended_stage,
                        "evidence": "Extracted from buying signals and stage alignment.",
                        "confidence_score": 0.85,
                        "details": results["crm_recommendation"].recommended_field_updates
                    },
                    source_transcript_id="trans_temp"
                )
                
            st.success("Analysis Completed! Navigate to subsequent tabs to view results.")

# Page 3: Summary
with tab3:
    st.header("Meeting Summary")
    if not st.session_state.analysis_complete:
        st.info("Analysis has not been run yet. Go to Tab 2 to run it.")
    else:
        st.markdown(f"### Executive Summary\n{st.session_state.summary.summary}")
        
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Action Items")
            for item in st.session_state.summary.action_items:
                st.write(f"- {item}")
        with col2:
            st.subheader("Follow-up Tasks")
            for task in st.session_state.summary.follow_up_tasks:
                st.write(f"- {task}")

# Page 4: Buying Signals
with tab4:
    st.header("Buying Signals")
    if not st.session_state.analysis_complete:
        st.info("Analysis has not been run yet.")
    else:
        for idx, signal in enumerate(st.session_state.signals.buying_signals):
            st.markdown(f"<div class='metric-card'><h4>Signal #{idx+1}</h4><p>{signal}</p></div>", unsafe_allow_html=True)

# Page 5: Sentiment
with tab5:
    st.header("Customer Sentiment")
    if not st.session_state.analysis_complete:
        st.info("Analysis has not been run yet.")
    else:
        st.subheader("Detected Sentiment")
        st.info(st.session_state.signals.customer_sentiment)

# Page 6: Competitor Mentions
with tab6:
    st.header("Competitor Mentions")
    if not st.session_state.analysis_complete:
        st.info("Analysis has not been run yet.")
    else:
        mentions = st.session_state.signals.competitor_mentions
        if not mentions:
            st.write("No competitors mentioned in this call.")
        else:
            for mention in mentions:
                st.write(f"- {mention}")

# Page 7: Proposed Updates
with tab7:
    st.header("Review Proposed CRM Updates")
    pending_list = crm_service.get_pending_updates()
    
    if not pending_list:
        st.success("No pending updates to review!")
    else:
        for update in pending_list:
            up_id = update["id"]
            changes = json.loads(update["proposed_changes"])
            
            st.markdown(f"### Proposed Update ID: {up_id} (Target: {update['target_table']} #{update['target_id']})")
            
            # Display target fields
            col_target, col_details = st.columns(2)
            with col_target:
                st.markdown(f"**Target Stage**: `{changes.get('stage')}`")
                st.markdown(f"**Confidence Score**: `{changes.get('confidence_score', 'N/A')}`")
            with col_details:
                st.markdown("**Updates details**:")
                st.json(changes.get("details", {}))
                
            st.markdown("**Transcript Evidence**:")
            st.markdown(f"<div class='evidence-box'>{changes.get('evidence', 'No specific evidence specified.')}</div>", unsafe_allow_html=True)
            
            # Action controls
            st.markdown("#### Actions:")
            act_col1, act_col2, act_col3 = st.columns(3)
            
            with act_col1:
                # Approve
                if st.button(f"Approve Update #{up_id}", key=f"app_{up_id}"):
                    if crm_service.commit_crm_update(up_id):
                        st.success(f"Update #{up_id} successfully committed!")
                        st.rerun()
            with act_col2:
                # Reject
                if st.button(f"Reject Update #{up_id}", key=f"rej_{up_id}"):
                    if crm_service.reject_crm_update(up_id):
                        st.warning(f"Update #{up_id} discarded.")
                        st.rerun()
            with act_col3:
                # Edit
                new_stage = st.text_input(f"Override Stage for #{up_id}", value=changes.get('stage'), key=f"edit_stage_{up_id}")
                if st.button(f"Save Edit #{up_id}", key=f"save_edit_{up_id}"):
                    changes['stage'] = new_stage
                    # Update database with edits
                    db.execute(
                        "UPDATE pending_updates SET proposed_changes = ? WHERE id = ?",
                        (json.dumps(changes), up_id)
                    )
                    st.success(f"Stage overridden for Update #{up_id}")
                    st.rerun()
                    
            st.divider()
