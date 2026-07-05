"""
Unit tests for guardrails and security-critical paths.

Covers:
- Prompt-injection detection in before_tool_callback
- PII redaction (credit-card and SSN patterns)
- CRM stage allow-list enforcement
- SQL column allow-list enforcement in CRMService
- DatabaseHelper WAL-mode pragma on open
"""
import json
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.agents.pipeline import (
    _redact_sensitive_info,
    before_tool_callback,
)
from src.database.db_helper import DatabaseHelper
from src.services.crm_service import CRMService
from src.utils.config import (
    INJECTION_PHRASES,
    VALID_DEAL_STAGES,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    email TEXT UNIQUE,
    phone TEXT,
    company TEXT,
    job_title TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS deals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_id INTEGER,
    name TEXT NOT NULL,
    amount REAL,
    stage TEXT NOT NULL,
    status TEXT DEFAULT 'open',
    close_date DATE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS pending_updates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_transcript_id TEXT,
    target_table TEXT NOT NULL,
    target_id INTEGER,
    proposed_changes TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT NOT NULL,
    target_table TEXT NOT NULL,
    target_id INTEGER NOT NULL,
    change_details TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""


def _make_db() -> tuple[DatabaseHelper, Path]:
    """Create an isolated in-process SQLite DB for testing."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db = DatabaseHelper(tmp.name)
    db.open()
    db._connection.executescript(SCHEMA_SQL)
    db._connection.commit()
    return db, Path(tmp.name)


# ---------------------------------------------------------------------------
# PII Redaction
# ---------------------------------------------------------------------------


class TestRedactSensitiveInfo:
    def test_credit_card_16_digits(self):
        raw = "Card number 4111222233334444 was used."
        assert "[REDACTED CREDIT CARD]" in _redact_sensitive_info(raw)

    def test_credit_card_with_spaces(self):
        raw = "Card: 4111 2222 3333 4444"
        assert "[REDACTED CREDIT CARD]" in _redact_sensitive_info(raw)

    def test_ssn_dashes(self):
        raw = "SSN is 123-45-6789."
        assert "[REDACTED SSN/SIN]" in _redact_sensitive_info(raw)

    def test_sin_spaces(self):
        raw = "SIN 123 456 789."
        assert "[REDACTED SSN/SIN]" in _redact_sensitive_info(raw)

    def test_clean_text_unchanged(self):
        raw = "No sensitive data here at all."
        assert _redact_sensitive_info(raw) == raw

    def test_multiple_patterns(self):
        raw = "CC 4111222233334444 and SSN 123-45-6789 both redacted."
        result = _redact_sensitive_info(raw)
        assert "[REDACTED CREDIT CARD]" in result
        assert "[REDACTED SSN/SIN]" in result


# ---------------------------------------------------------------------------
# Prompt-Injection Detection
# ---------------------------------------------------------------------------


class TestInjectionPhraseList:
    def test_all_phrases_are_lowercase(self):
        """Phrases must be lowercase so .lower() comparison works correctly."""
        for phrase in INJECTION_PHRASES:
            assert phrase == phrase.lower(), f"Phrase not lowercase: {phrase!r}"

    def test_phrases_are_non_empty(self):
        assert len(INJECTION_PHRASES) >= 4


class TestBeforeToolCallback:
    """Tests for before_tool_callback guardrail."""

    def _make_tool(self, name="propose_crm_update"):
        tool = MagicMock()
        tool.name = name
        return tool

    def _make_ctx(self):
        return MagicMock()

    # --- Tool allow-list ---

    @pytest.mark.asyncio
    async def test_blocked_tool_raises(self):
        tool = self._make_tool(name="delete_all_deals")
        with pytest.raises(ValueError, match="Blocked tool"):
            await before_tool_callback(tool, {}, self._make_ctx())

    @pytest.mark.asyncio
    async def test_allowed_tool_passes(self):
        tool = self._make_tool(name="propose_crm_update")
        args = {"recommended_stage": "Qualified", "recommended_field_updates": {}}
        result = await before_tool_callback(tool, args, self._make_ctx())
        assert result is None

    # --- Injection detection ---

    @pytest.mark.asyncio
    @pytest.mark.parametrize("phrase", [
        "ignore previous instructions",
        "system prompt",
        "jailbreak",
        "act as",
    ])
    async def test_injection_phrase_blocked(self, phrase):
        tool = self._make_tool()
        args = {
            "recommended_stage": "Qualified",
            "recommended_field_updates": {"note": f"Please {phrase} now"},
        }
        with pytest.raises(ValueError, match="Blocked"):
            await before_tool_callback(tool, args, self._make_ctx())

    # --- Stage allow-list ---

    @pytest.mark.asyncio
    async def test_invalid_stage_blocked(self):
        tool = self._make_tool()
        args = {"recommended_stage": "EvilStage", "recommended_field_updates": {}}
        with pytest.raises(ValueError, match="invalid CRM stage"):
            await before_tool_callback(tool, args, self._make_ctx())

    @pytest.mark.asyncio
    @pytest.mark.parametrize("stage", VALID_DEAL_STAGES)
    async def test_valid_stages_pass(self, stage):
        tool = self._make_tool()
        args = {"recommended_stage": stage, "recommended_field_updates": {}}
        result = await before_tool_callback(tool, args, self._make_ctx())
        assert result is None


# ---------------------------------------------------------------------------
# CRMService column allow-list
# ---------------------------------------------------------------------------


class TestCRMServiceColumnAllowList:
    """Ensure _apply_changes_to_table silently drops unknown columns."""

    def setup_method(self):
        self.db, self.db_path = _make_db()
        # Seed a deal row
        self.db.execute(
            "INSERT INTO deals (contact_id, name, amount, stage, status) VALUES (?,?,?,?,?)",
            (None, "Test Deal", 10000.0, "Prospecting", "open"),
        )
        self.svc = CRMService(self.db)

    def teardown_method(self):
        self.db.close()
        self.db_path.unlink(missing_ok=True)

    def test_known_column_is_applied(self):
        self.svc._apply_changes_to_table("deals", 1, {"stage": "Qualified"})
        row = self.db.fetch_one("SELECT stage FROM deals WHERE id = 1")
        assert row["stage"] == "Qualified"

    def test_unknown_column_is_dropped(self):
        """An AI-injected column name must not reach the SQL SET clause."""
        self.svc._apply_changes_to_table(
            "deals", 1, {"stage": "Proposal", "drop_table": "deals"}
        )
        row = self.db.fetch_one("SELECT stage FROM deals WHERE id = 1")
        assert row["stage"] == "Proposal"

    def test_unknown_table_is_skipped(self):
        """Non-allow-listed tables must be silently skipped."""
        # Should not raise
        self.svc._apply_changes_to_table("admin_users", 1, {"stage": "Hack"})


# ---------------------------------------------------------------------------
# DatabaseHelper WAL mode
# ---------------------------------------------------------------------------


class TestDatabaseHelperPragmas:
    def test_wal_mode_enabled(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = tmp.name
        try:
            db = DatabaseHelper(db_path)
            conn = db.open()
            row = conn.execute("PRAGMA journal_mode;").fetchone()
            assert row[0] == "wal", f"Expected WAL mode, got: {row[0]}"
            db.close()
        finally:
            Path(db_path).unlink(missing_ok=True)

    def test_foreign_keys_enabled(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = tmp.name
        try:
            db = DatabaseHelper(db_path)
            conn = db.open()
            row = conn.execute("PRAGMA foreign_keys;").fetchone()
            assert row[0] == 1, "Foreign keys should be ON"
            db.close()
        finally:
            Path(db_path).unlink(missing_ok=True)
