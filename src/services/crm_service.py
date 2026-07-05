"""
CRMService — business operations on CRM data.

Responsibilities:
- Query pending_updates awaiting human review.
- Create new AI-proposed updates.
- Commit (approve) a pending update, apply it to the target table, and write an audit log.
- Reject a pending update and write an audit log.

All audit log entries capture:
  ai_suggestion   – the original AI-proposed changes (unmodified)
  human_edits     – the changes that were actually committed (may differ from AI suggestion)
  status          – "approved" | "rejected"
  approver        – name of the human who took the action
"""
import json
import logging
import sqlite3
from typing import Optional

from src.database.db_helper import DatabaseHelper
from src.utils.config import ALLOWED_DB_COLUMNS, NON_COLUMN_FIELDS
from src.utils.logging_config import get_logger

logger = get_logger(__name__)

# DB columns that are never written to contacts / deals tables
_NON_COLUMN_FIELDS: frozenset[str] = NON_COLUMN_FIELDS

# Allow-list of writable columns per table — prevents SQL column injection
# from AI-generated field names embedded in the recommended_field_updates dict.
_ALLOWED_COLUMNS: dict[str, frozenset[str]] = ALLOWED_DB_COLUMNS


class CRMService:
    """Service layer for CRM contacts, deals, pending updates, and audit logs."""

    def __init__(self, db_helper: DatabaseHelper) -> None:
        self.db = db_helper

    # ------------------------------------------------------------------
    # Pending updates — read
    # ------------------------------------------------------------------

    def get_pending_updates(self) -> list[dict]:
        """Return all updates whose status is 'pending'."""
        return self.db.fetch_all(
            "SELECT * FROM pending_updates WHERE status = 'pending'"
        )

    # ------------------------------------------------------------------
    # Pending updates — create
    # ------------------------------------------------------------------

    def create_pending_update(
        self,
        target_table: str,
        target_id: int,
        proposed_changes: dict,
        source_transcript_id: Optional[str] = None,
    ) -> int:
        """
        Persist a new AI-proposed CRM update for human review.

        Args:
            target_table:         "contacts" or "deals".
            target_id:            Primary key of the record to be updated.
            proposed_changes:     Dict of field → value pairs (plus metadata fields).
            source_transcript_id: Filename or ID of the originating transcript.

        Returns:
            The ``id`` of the newly created ``pending_updates`` row.
        """
        logger.info(
            "Creating pending update: table=%s id=%s transcript=%s",
            target_table, target_id, source_transcript_id,
        )
        return self.db.execute(
            """
            INSERT INTO pending_updates
                (source_transcript_id, target_table, target_id, proposed_changes, status)
            VALUES (?, ?, ?, ?, 'pending')
            """,
            (source_transcript_id, target_table, target_id, json.dumps(proposed_changes)),
        )

    # ------------------------------------------------------------------
    # Pending updates — approve
    # ------------------------------------------------------------------

    def commit_crm_update(
        self,
        pending_update_id: int,
        overridden_changes: Optional[dict] = None,
        approver: str = "Sales Ops Manager",
    ) -> bool:
        """
        Approve a pending update.

        Steps:
        1. Load the pending update; bail if it no longer exists or is not pending.
        2. Apply *overridden_changes* (human edits) if provided, otherwise apply the
           original AI suggestion.
        3. Write the resolved changes to the target table (contacts or deals).
        4. Mark the pending update as 'approved'.
        5. Append a structured entry to audit_logs.

        Args:
            pending_update_id: PK of the ``pending_updates`` row.
            overridden_changes: Human-edited replacement for the AI suggestion. When
                                ``None``, the original AI suggestion is committed as-is.
            approver:           Name of the approving user (shown in audit log).

        Returns:
            ``True`` on success, ``False`` when the update was not found or not pending.
        """
        update = self.db.fetch_one(
            "SELECT * FROM pending_updates WHERE id = ?", (pending_update_id,)
        )
        if not update or update["status"] != "pending":
            logger.warning("commit_crm_update: update %s not found or not pending.", pending_update_id)
            return False

        target_table: str = update["target_table"]
        target_id: int = update["target_id"]
        ai_suggestion: dict = json.loads(update["proposed_changes"])

        # Human edits take precedence over the original AI proposal
        committed_changes: dict = overridden_changes if overridden_changes is not None else ai_suggestion

        # --- Apply to target table ---
        self._apply_changes_to_table(target_table, target_id, committed_changes)

        # --- Mark pending update as approved ---
        self.db.execute(
            "UPDATE pending_updates SET status = 'approved' WHERE id = ?",
            (pending_update_id,),
        )

        # --- Audit log ---
        self._write_audit_log(
            action="APPROVE_UPDATE",
            target_table=target_table,
            target_id=target_id,
            ai_suggestion=ai_suggestion,
            human_edits=committed_changes,
            status="approved",
            approver=approver,
        )

        logger.info(
            "Approved pending_update %s on %s#%s by %s",
            pending_update_id, target_table, target_id, approver,
        )
        return True

    # ------------------------------------------------------------------
    # Pending updates — reject
    # ------------------------------------------------------------------

    def reject_crm_update(
        self,
        pending_update_id: int,
        approver: str = "Sales Ops Manager",
    ) -> bool:
        """
        Reject (discard) a pending update.

        The target table is left untouched.  The audit log records the original
        AI suggestion so the decision can be reviewed later.

        Args:
            pending_update_id: PK of the ``pending_updates`` row.
            approver:          Name of the rejecting user (shown in audit log).

        Returns:
            ``True`` on success, ``False`` when the update was not found or not pending.
        """
        update = self.db.fetch_one(
            "SELECT * FROM pending_updates WHERE id = ?", (pending_update_id,)
        )
        if not update or update["status"] != "pending":
            logger.warning("reject_crm_update: update %s not found or not pending.", pending_update_id)
            return False

        self.db.execute(
            "UPDATE pending_updates SET status = 'rejected' WHERE id = ?",
            (pending_update_id,),
        )

        self._write_audit_log(
            action="REJECT_UPDATE",
            target_table=update["target_table"],
            target_id=update["target_id"] or 0,
            ai_suggestion=json.loads(update["proposed_changes"]),
            human_edits=None,
            status="rejected",
            approver=approver,
        )

        logger.info(
            "Rejected pending_update %s by %s", pending_update_id, approver
        )
        return True

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _apply_changes_to_table(
        self, target_table: str, target_id: int, changes: dict
    ) -> None:
        """
        Build and execute a parameterised UPDATE on *target_table*.

        Metadata keys (evidence, confidence_score, details) are stripped before
        the update.  The nested ``details`` dict, if present, is flattened into
        the top-level field set so its key/value pairs reach the database.

        Args:
            target_table: "contacts" or "deals".
            target_id:    Primary key of the row to update.
            changes:      Dict that may contain both real column names and metadata keys.
        """
        if target_table not in ("contacts", "deals"):
            logger.warning("_apply_changes_to_table: unknown table '%s'; skipping.", target_table)
            return

        # Remove metadata-only keys; flatten nested 'details' dict
        db_updates: dict = {k: v for k, v in changes.items() if k not in _NON_COLUMN_FIELDS}
        if isinstance(changes.get("details"), dict):
            db_updates.update(changes["details"])

        # SECURITY: validate column names against the per-table allow-list.
        # AI-produced recommended_field_updates may contain arbitrary key names;
        # injecting them directly into an f-string SET clause is an SQL injection risk.
        allowed: frozenset[str] = _ALLOWED_COLUMNS.get(target_table, frozenset())
        invalid_cols = set(db_updates) - allowed
        if invalid_cols:
            logger.warning(
                "_apply_changes_to_table: rejecting unknown columns for %s: %s",
                target_table, invalid_cols,
            )
        db_updates = {k: v for k, v in db_updates.items() if k in allowed}

        if not db_updates:
            logger.debug("_apply_changes_to_table: no valid column updates to apply.")
            return

        # Build parameterised SET clause — column names are validated above,
        # so f-string interpolation here is safe.
        set_clause = ", ".join(f"{col} = ?" for col in db_updates)
        params: tuple = (*db_updates.values(), target_id)

        try:
            self.db.execute(
                f"UPDATE {target_table} SET {set_clause} WHERE id = ?",  # noqa: S608
                params,
            )
        except sqlite3.Error:
            logger.exception(
                "Failed to apply changes to %s#%s", target_table, target_id
            )
            raise

    def _write_audit_log(
        self,
        action: str,
        target_table: str,
        target_id: int,
        ai_suggestion: dict,
        human_edits: Optional[dict],
        status: str,
        approver: str,
    ) -> None:
        """Insert a structured row into audit_logs."""
        payload = {
            "ai_suggestion": ai_suggestion,
            "human_edits": human_edits,
            "status": status,
            "approver": approver,
        }
        self.db.execute(
            """
            INSERT INTO audit_logs (action, target_table, target_id, change_details)
            VALUES (?, ?, ?, ?)
            """,
            (action, target_table, target_id, json.dumps(payload)),
        )
