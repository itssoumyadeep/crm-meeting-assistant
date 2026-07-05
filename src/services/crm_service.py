import json
from src.database.db_helper import DatabaseHelper

class CRMService:
    """
    Service class handling operations related to contacts, deals, pending updates, and audit logs.
    """
    def __init__(self, db_helper: DatabaseHelper):
        self.db = db_helper

    def get_pending_updates(self) -> list:
        """Retrieves all pending updates from the database."""
        query = "SELECT * FROM pending_updates WHERE status = 'pending'"
        return self.db.fetch_all(query)

    def create_pending_update(self, target_table: str, target_id: int, proposed_changes: dict, source_transcript_id: str = None) -> int:
        """Inserts a new proposed update into pending_updates."""
        query = """
            INSERT INTO pending_updates (source_transcript_id, target_table, target_id, proposed_changes, status)
            VALUES (?, ?, ?, ?, 'pending')
        """
        changes_json = json.dumps(proposed_changes)
        return self.db.execute(query, (source_transcript_id, target_table, target_id, changes_json))

    def commit_crm_update(self, pending_update_id: int, overridden_changes: dict = None, approver: str = "Sales Ops Manager") -> bool:
        """
        Approves the proposed updates, applies changes to target table, 
        and records the operation in audit logs.
        """
        # 1. Fetch proposed update
        update = self.db.fetch_one("SELECT * FROM pending_updates WHERE id = ?", (pending_update_id,))
        if not update or update["status"] != "pending":
            return False

        target_table = update["target_table"]
        target_id = update["target_id"]
        ai_suggestion = json.loads(update["proposed_changes"])

        # Use overrides if provided (human edits)
        committed_changes = overridden_changes if overridden_changes is not None else ai_suggestion

        # 2. Update target table
        if target_table in ("contacts", "deals"):
            # Exclude non-column fields like evidence and confidence_score
            db_updates = {k: v for k, v in committed_changes.items() if k not in ("evidence", "confidence_score", "details")}
            if "details" in committed_changes and isinstance(committed_changes["details"], dict):
                db_updates.update(committed_changes["details"])
                
            fields = []
            params = []
            for col, val in db_updates.items():
                fields.append(f"{col} = ?")
                params.append(val)
            
            if fields:
                params.append(target_id)
                update_query = f"UPDATE {target_table} SET {', '.join(fields)} WHERE id = ?"
                self.db.execute(update_query, tuple(params))

        # 3. Update pending_updates status
        self.db.execute(
            "UPDATE pending_updates SET status = 'approved' WHERE id = ?", 
            (pending_update_id,)
        )

        # 4. Log to audit_logs
        audit_payload = {
            "ai_suggestion": ai_suggestion,
            "human_edits": committed_changes,
            "status": "approved",
            "approver": approver
        }
        self.db.execute(
            """
            INSERT INTO audit_logs (action, target_table, target_id, change_details)
            VALUES ('APPROVE_UPDATE', ?, ?, ?)
            """,
            (target_table, target_id, json.dumps(audit_payload))
        )
        return True

    def reject_crm_update(self, pending_update_id: int, approver: str = "Sales Ops Manager") -> bool:
        """Discards a pending update by setting its status to rejected."""
        update = self.db.fetch_one("SELECT * FROM pending_updates WHERE id = ?", (pending_update_id,))
        if not update or update["status"] != "pending":
            return False

        # Update status
        self.db.execute(
            "UPDATE pending_updates SET status = 'rejected' WHERE id = ?", 
            (pending_update_id,)
        )

        # Log to audit_logs
        audit_payload = {
            "ai_suggestion": json.loads(update["proposed_changes"]),
            "human_edits": None,
            "status": "rejected",
            "approver": approver
        }
        self.db.execute(
            """
            INSERT INTO audit_logs (action, target_table, target_id, change_details)
            VALUES ('REJECT_UPDATE', ?, ?, ?)
            """,
            (update["target_table"], update["target_id"] or 0, json.dumps(audit_payload))
        )
        return True

