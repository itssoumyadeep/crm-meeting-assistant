# 💼 CRM Meeting Assistant

> **AI-powered sales copilot** — paste a meeting transcript, get a structured analysis, and sync approved updates to your CRM in one click.

Built with **Google ADK** (multi-agent pipeline), **MCP** (Model Context Protocol server), **Streamlit** (human-in-the-loop UI), and **SQLite** (local CRM store). Designed for hackathon demo and rapid prototyping.

---

## Architecture

```mermaid
flowchart TD
    subgraph UI["Streamlit UI  (src/ui/app.py)"]
        T1["📝 Paste Transcript"]
        T2["⚡ Run Analysis"]
        T3["📋 Summary"]
        T4["📈 Buying Signals"]
        T5["❤️ Sentiment"]
        T6["⚔️ Competitors"]
        T7["🔄 Propose → Approve / Reject"]
        T8["📜 Audit Trail"]
    end

    subgraph ADK["ADK Pipeline  (src/agents/pipeline.py)"]
        TA["TranscriptAgent\noutput_schema=TranscriptSummary"]
        SA["SignalAgent\noutput_schema=Signals"]
        CRM["CRMMapperAgent\noutput_schema=CRMRecommendation\nbefore_tool_callback ← guardrails"]
    end

    subgraph Guardrails["Guardrail Layer"]
        G1["✅ Tool allow-list\n(propose_crm_update only)"]
        G2["🛡️ Prompt-injection scan\n(OWASP LLM Top-10 phrases)"]
        G3["📋 Stage allow-list\n(Prospecting → Closed Lost)"]
        G4["🔒 PII redaction\n(CC + SSN/SIN regex)"]
    end

    subgraph MCP["MCP Server  (src/mcp_server/server.py)"]
        M1["get_contact(name)"]
        M2["get_deal_stage_options()"]
    end

    subgraph DB["SQLite  (crm_assistant.db)"]
        DB1[("contacts")]
        DB2[("deals")]
        DB3[("pending_updates")]
        DB4[("audit_logs")]
    end

    T1 -->|transcript text| T2
    T2 -->|asyncio.run| ADK
    TA -->|transcript_summary| SA
    SA -->|signals| CRM
    CRM --> Guardrails
    Guardrails -->|propose_crm_update| DB3
    MCP --> DB1
    MCP --> DB2
    CRM -.->|reads stage options| MCP
    T7 -->|approve / reject / edit| DB3
    T7 -->|commit_crm_update| DB2
    T7 -->|write_audit_log| DB4
    T8 --> DB4
    ADK --> T3
    ADK --> T4
    ADK --> T5
    ADK --> T6
```

### Key Design Decisions

| Area | Decision | Rationale |
|---|---|---|
| **Multi-agent** | `SequentialAgent`: TranscriptAgent → SignalAgent → CRMMapperAgent | Each stage enriches session state; downstream agents see previous outputs |
| **Structured output** | `output_schema=Pydantic` on each agent | Eliminates JSON parsing fragility; enforces typed contracts between agents |
| **Guardrails** | `before_tool_callback` on `CRMMapperAgent` | Blocks rogue tool calls, injection phrases, invalid stages, and PII before any write |
| **Human-in-the-loop** | `pending_updates` table + Tab 7 review UI | **No AI output ever reaches the CRM directly** — every write requires human Approve/Edit/Reject |
| **MCP server** | `FastMCP` exposing read-only contact and stage queries | Agents get structured data access without direct DB coupling |
| **SQLite WAL** | `PRAGMA journal_mode = WAL` + `busy_timeout = 5000` | Prevents "database is locked" errors under Streamlit's concurrent rendering |
| **Column security** | `ALLOWED_DB_COLUMNS` allow-list per table | Prevents AI-generated field names from injecting arbitrary columns into the SQL `SET` clause |

---

## Prerequisites

| Tool | Install |
|---|---|
| **uv** | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| **agents-cli** | `uv tool install google-agents-cli` |
| **Google Cloud SDK** | [cloud.google.com/sdk](https://cloud.google.com/sdk/docs/install) |
| Python ≥ 3.11 | Managed by `uv` automatically |

---

## Quick Start (Hackathon Demo)

### 1. Clone & install

```bash
git clone <repo-url>
cd crm-meeting-assistant
agents-cli install
```

### 2. Configure credentials

```bash
cp .env.example .env
```

**Option A — Vertex AI (recommended for GCP projects):**
```bash
# In .env:
GOOGLE_GENAI_USE_VERTEXAI=true
GOOGLE_CLOUD_PROJECT=your-gcp-project-id
GOOGLE_CLOUD_LOCATION=global

# Authenticate:
gcloud auth application-default login
```

**Option B — Google AI Studio (fastest for hackathon, no GCP needed):**
```bash
# In .env, comment out Vertex lines and set:
GEMINI_API_KEY=your-api-key-from-aistudio.google.com
```

### 3. Seed demo data

```bash
uv run python -m src.database.populate_demo
# ✅  SQLite database populated with demo data.
```

### 4. Launch the UI

```bash
uv run streamlit run src/ui/app.py
# → Opens at http://localhost:8501
```

### 5. Demo flow (5-minute walkthrough)

| Step | Tab | What to do |
|---|---|---|
| 1 | **1 – Paste Transcript** | Select `normal_sales_call.txt` from the dropdown |
| 2 | **2 – Run Analysis** | Click **▶ Start AI Analysis** (30–60 s) |
| 3 | **3 – Summary** | Read the executive summary and action items |
| 4 | **4 – Buying Signals** | See positive/negative deal signals |
| 5 | **5 – Sentiment** | Check overall prospect sentiment |
| 6 | **6 – Competitors** | See any mentioned competitors |
| 7 | **7 – Proposed Updates** | Enter your name, optionally edit the stage, click **✅ Approve** |
| 8 | **8 – Activity History** | Confirm the audit trail recorded the decision |

> **Tip:** Try `prompt_injection_attempt.txt` to demo the guardrails blocking the attack live.

---

## All Commands

| Command | Purpose |
|---|---|
| `uv run streamlit run src/ui/app.py` | Launch the Streamlit demo UI |
| `uv run python -m src.database.populate_demo` | Re-seed demo SQLite data |
| `agents-cli playground` | Interactive ADK playground |
| `uv run pytest tests/unit tests/integration -v` | Run all tests |
| `agents-cli lint` | Run ruff + codespell |
| `agents-cli eval generate` | Run agent on eval dataset |
| `agents-cli eval grade` | Grade agent traces |
| `agents-cli eval compare` | Regression diff between two runs |
| `agents-cli eval optimize` | Auto-tune prompts via eval data |
| `agents-cli deploy` | Deploy to Cloud Run (requires GCP) |

---

## Project Structure

```
crm-meeting-assistant/
├── app/                          # ADK app (FastAPI + A2A deployment entry point)
│   ├── agent.py                  # Root ParallelAgent pipeline
│   ├── crm_mcp_server.py         # Standalone stdio MCP server (in-memory demo)
│   └── fast_api_app.py           # FastAPI + A2A server
│
├── src/
│   ├── agents/
│   │   ├── pipeline.py           # SequentialAgent pipeline (Streamlit UI path)
│   │   └── schemas.py            # Pydantic output schemas (typed agent contracts)
│   ├── database/
│   │   ├── db_helper.py          # SQLite helper (WAL, FK, error-safe queries)
│   │   ├── schema.sql            # Table DDL + covering indexes
│   │   └── populate_demo.py      # Demo data seeder
│   ├── mcp_server/
│   │   └── server.py             # FastMCP read-only CRM tools
│   ├── services/
│   │   └── crm_service.py        # pending_updates lifecycle + audit log
│   ├── skills/
│   │   └── deal-scoring-skill/
│   │       └── playbook.md       # Deal-scoring rules injected into CRMMapperAgent
│   ├── ui/
│   │   └── app.py                # 8-tab Streamlit UI
│   └── utils/
│       ├── config.py             # All constants (env-var overrideable)
│       └── logging_config.py     # Centralised logger factory
│
├── sample_data/transcripts/      # 4 demo scenarios (normal, competitor, stalled, injection)
├── tests/
│   ├── unit/
│   │   ├── test_dummy.py         # Placeholder (kept for scaffold compat)
│   │   └── test_guardrails.py    # Guardrail, PII, column allow-list tests
│   └── integration/              # (extend here)
├── .env.example                  # Credential template
├── pyproject.toml                # uv / ruff / pytest config
└── Dockerfile                    # Cloud Run container
```

---

## Security Model

```
Transcript (untrusted)
    ↓
TranscriptAgent / SignalAgent   ← read-only; no tool calls
    ↓
CRMMapperAgent  ←  before_tool_callback runs:
    ├─ Tool allow-list          (only propose_crm_update)
    ├─ Prompt-injection scan    (OWASP LLM Top-10 phrases)
    ├─ CRM stage allow-list     (Prospecting → Closed Lost)
    └─ PII redaction            (CC numbers, SSN/SIN)
    ↓
pending_updates table           ← staged, NOT yet committed
    ↓
Human review (Tab 7)            ← Approve / Edit / Reject
    ↓
_apply_changes_to_table  ←  column allow-list per table
    ↓
deals / contacts                ← committed
    ↓
audit_logs                      ← immutable record of every decision
```

---

## Running Tests

```bash
uv run pytest tests/unit tests/integration -v
```

Covers:
- Prompt-injection blocking via `before_tool_callback`
- PII redaction (credit card + SSN/SIN patterns)
- CRM stage allow-list enforcement
- SQL column allow-list (blocks AI column injection)
- SQLite WAL mode and foreign-key pragma verification

---

## Future Improvements

### Near-term
- [ ] **Deal selection UI** — let users choose which deal to attach the analysis to (replace placeholder `target_id=1`)
- [ ] **Parallel pipeline in Streamlit** — mirror the `ParallelAgent` pattern from `app/agent.py` for 5× faster analysis
- [ ] **Streaming progress** — use ADK's event stream to show per-agent status in real time instead of a single spinner
- [ ] **Eval dataset** — run `agents-cli eval dataset synthesize`; build 10+ graded scenarios; use `agents-cli eval optimize` to tune prompts

### Medium-term
- [ ] **Live MCP integration** — wire `src/mcp_server/server.py` into the pipeline via `MCPToolset` so agents query live contacts/deals
- [ ] **Meetings table** — link transcripts ↔ meetings ↔ deals via proper FK relationships
- [ ] **OAuth approver identity** — replace free-text approver name with Google Identity (IAP or Firebase Auth)
- [ ] **Webhook on approval** — fire a Pub/Sub event or Salesforce API call on approve, enabling real CRM sync

### Long-term
- [ ] **Persistent sessions** — swap `InMemorySessionService` for `DatabaseSessionService` (Firestore / Cloud SQL) for multi-user support
- [ ] **A2A interoperability** — expose the pipeline as an A2A agent for programmatic invocation by other agents
- [ ] **BigQuery analytics** — stream audit logs to BigQuery for win-rate and deal-velocity dashboards
- [ ] **Voice input** — integrate Speech-to-Text so reps can record calls directly instead of pasting transcripts

---

## License

Apache 2.0 — see `LICENSE` for details.
