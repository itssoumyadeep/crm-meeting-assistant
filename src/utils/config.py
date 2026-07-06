"""
Centralised configuration for the CRM Meeting Assistant.

All environment-sensitive values live here. Each setting reads from an
environment variable first; if the variable is absent, a safe default is used.
No code outside this module should call `os.environ` directly.
"""
import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Project root (two levels up from src/utils/config.py)
# ---------------------------------------------------------------------------
PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
#: Path to the SQLite database file.
DB_PATH: Path = Path(os.environ.get("CRM_DB_PATH", str(PROJECT_ROOT / "crm_assistant.db")))

#: Path to the SQL schema initialisation file.
SCHEMA_PATH: Path = PROJECT_ROOT / "src" / "database" / "schema.sql"

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
#: Directory that holds the sample transcript text files.
SAMPLE_TRANSCRIPTS_DIR: Path = PROJECT_ROOT / "sample_data" / "transcripts"

#: Path to the deal-scoring playbook injected into the CRM Mapper agent.
PLAYBOOK_PATH: Path = PROJECT_ROOT / "src" / "skills" / "deal-scoring-skill" / "playbook.md"

#: Path to the transcript-handoff playbook injected into the Transcript agent.
TRANSCRIPT_PLAYBOOK_PATH: Path = PROJECT_ROOT / "src" / "skills" / "transcript-handoff-skill" / "playbook.md"

# ---------------------------------------------------------------------------
# ADK / Gemini
# ---------------------------------------------------------------------------
#: LLM model identifier.  Never changed here — override via env var only.
MODEL_NAME: str = os.environ.get("CRM_MODEL_NAME", "gemini-flash-latest")

#: Number of automatic LLM call retries on transient errors.
MODEL_RETRY_ATTEMPTS: int = int(os.environ.get("CRM_MODEL_RETRY_ATTEMPTS", "3"))

#: ADK app name used when creating/querying sessions.
ADK_APP_NAME: str = "crm_assistant"

# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------
MCP_SERVER_NAME: str = "CRM Meeting Assistant Server"

# ---------------------------------------------------------------------------
# Guardrails
# ---------------------------------------------------------------------------
#: Phrases whose presence in any tool argument triggers a hard block.
#: Covers the most common prompt-injection patterns in the OWASP LLM Top-10.
INJECTION_PHRASES: tuple[str, ...] = (
    "ignore previous instructions",
    "ignore all previous",
    "forget previous instructions",
    "disregard",
    "system prompt",
    "as an ai",
    "you are now",
    "act as",
    "jailbreak",
    "new instructions",
    "override instructions",
    "reveal your prompt",
    "show your instructions",
    "print your system",
)

#: The only tool name that crm_mapper_agent is allowed to invoke.
ALLOWED_TOOL_NAME: str = "propose_crm_update"

# ---------------------------------------------------------------------------
# CRM domain constants  (single source of truth, shared with MCP server)
# ---------------------------------------------------------------------------
VALID_DEAL_STAGES: tuple[str, ...] = (
    "Prospecting",
    "Qualified",
    "Proposal",
    "Negotiation",
    "Closed Won",
    "Closed Lost",
)

#: DB columns that must NOT be written to the target table (metadata only).
NON_COLUMN_FIELDS: frozenset[str] = frozenset({"evidence", "confidence_score", "details"})

#: Per-table allow-list of writable columns for CRMService._apply_changes_to_table.
#: Only these column names may appear in the SQL SET clause produced from
#: AI-generated recommended_field_updates — all others are silently dropped.
ALLOWED_DB_COLUMNS: dict[str, frozenset[str]] = {
    "deals": frozenset({
        "name", "amount", "stage", "status", "close_date", "contact_id",
    }),
    "contacts": frozenset({
        "first_name", "last_name", "email", "phone", "company", "job_title",
    }),
}
