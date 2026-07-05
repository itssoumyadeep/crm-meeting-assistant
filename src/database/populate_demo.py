"""
Demo data seeder for the CRM Meeting Assistant.

Drops all existing data and re-inserts two contacts, two deals, and two
AI-proposed pending updates — one per sample transcript — so the UI can
be demonstrated without running a live AI pipeline first.

Usage::

    uv run python -m src.database.populate_demo
    # or
    uv run python src/database/populate_demo.py
"""
import json
import logging

from src.database.db_helper import DatabaseHelper
from src.utils.config import DB_PATH, SCHEMA_PATH
from src.utils.logging_config import get_logger

logger = get_logger(__name__)


def populate() -> None:
    """Drop and re-seed all CRM demo data."""
    db = DatabaseHelper(DB_PATH)

    logger.info("Initialising database schema at %s", DB_PATH)
    db.initialize_database(SCHEMA_PATH)

    # --- Clean slate ---
    for table in ("audit_logs", "pending_updates", "deals", "contacts"):
        db.execute(f"DELETE FROM {table}")  # noqa: S608
        logger.debug("Cleared table: %s", table)

    # --- Contacts ---
    contact_acme_id = db.execute(
        "INSERT INTO contacts (first_name, last_name, email, company, job_title)"
        " VALUES (?, ?, ?, ?, ?)",
        ("John", "Doe", "john.doe@acme.com", "Acme Corp", "VP of Operations"),
    )
    contact_prospect_id = db.execute(
        "INSERT INTO contacts (first_name, last_name, email, company, job_title)"
        " VALUES (?, ?, ?, ?, ?)",
        ("Sarah", "Chen", "s.chen@prospect-org.com", "Prospect Org", "Head of Engineering"),
    )
    logger.info("Inserted contacts: %s, %s", contact_acme_id, contact_prospect_id)

    # --- Deals ---
    deal_acme_id = db.execute(
        "INSERT INTO deals (contact_id, name, amount, stage, status)"
        " VALUES (?, ?, ?, ?, ?)",
        (contact_acme_id, "Acme Corp Expansion Deal", 45_000.0, "Prospecting", "open"),
    )
    deal_prospect_id = db.execute(
        "INSERT INTO deals (contact_id, name, amount, stage, status)"
        " VALUES (?, ?, ?, ?, ?)",
        (contact_prospect_id, "Prospect Org Platform Migration", 30_000.0, "Qualified", "open"),
    )
    logger.info("Inserted deals: %s, %s", deal_acme_id, deal_prospect_id)

    # --- Pending updates ---
    _insert_pending_update(
        db,
        source_transcript="normal_sales_call.txt",
        deal_id=deal_acme_id,
        stage="Proposal",
        evidence="Customer confirmed a $45,000 budget and the VP of Operations signed off.",
        confidence=0.95,
        amount=45_000.0,
    )
    _insert_pending_update(
        db,
        source_transcript="competitor_mentioned.txt",
        deal_id=deal_prospect_id,
        stage="Proposal",
        evidence="Evaluating HubSpot, but open to alternatives within a $30,000 budget.",
        confidence=0.80,
        amount=30_000.0,
    )

    logger.info("Demo database seeded successfully.")
    print("✅  SQLite database populated with demo data.")


def _insert_pending_update(
    db: DatabaseHelper,
    source_transcript: str,
    deal_id: int,
    stage: str,
    evidence: str,
    confidence: float,
    amount: float,
) -> None:
    """Helper to insert a single pending_updates row."""
    proposed_changes = {
        "stage": stage,
        "evidence": evidence,
        "confidence_score": confidence,
        "details": {"amount": amount, "stage": stage},
    }
    db.execute(
        """
        INSERT INTO pending_updates
            (source_transcript_id, target_table, target_id, proposed_changes, status)
        VALUES (?, 'deals', ?, ?, 'pending')
        """,
        (source_transcript, deal_id, json.dumps(proposed_changes)),
    )
    logger.debug("Inserted pending update for deal %s from %s", deal_id, source_transcript)


if __name__ == "__main__":
    populate()
