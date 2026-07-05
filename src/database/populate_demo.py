import os
import json
from src.database.db_helper import DatabaseHelper

def populate():
    BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    DB_PATH = os.path.join(BASE_DIR, "crm_assistant.db")
    SCHEMA_PATH = os.path.join(BASE_DIR, "src", "database", "schema.sql")

    db = DatabaseHelper(DB_PATH)

    # Initialize tables if not already done
    db.initialize_database(SCHEMA_PATH)

    # Clear existing data to ensure clean demo state
    db.execute("DELETE FROM contacts")
    db.execute("DELETE FROM deals")
    db.execute("DELETE FROM pending_updates")
    db.execute("DELETE FROM audit_logs")

    # Insert contacts
    c1 = db.execute(
        "INSERT INTO contacts (first_name, last_name, email, company, job_title) VALUES (?, ?, ?, ?, ?)",
        ("John", "Doe", "john.doe@acme.com", "Acme Corp", "VP of Operations")
    )
    c2 = db.execute(
        "INSERT INTO contacts (first_name, last_name, email, company, job_title) VALUES (?, ?, ?, ?, ?)",
        ("Sarah", "Chen", "s.chen@hubspot-prospect.com", "Prospect Org", "Head of Engineering")
    )

    # Insert deals
    d1 = db.execute(
        "INSERT INTO deals (contact_id, name, amount, stage, status) VALUES (?, ?, ?, ?, ?)",
        (c1, "Acme Corp Expansion Deal", 45000.0, "Prospecting", "open")
    )
    d2 = db.execute(
        "INSERT INTO deals (contact_id, name, amount, stage, status) VALUES (?, ?, ?, ?, ?)",
        (c2, "Prospect Org Platform Migration", 30000.0, "Qualified", "open")
    )

    # Insert initial pending updates
    proposed_changes_1 = {
        "stage": "Proposal",
        "evidence": "Customer confirmed they have a $45,000 budget and the VP signed off.",
        "confidence_score": 0.95,
        "details": {
            "amount": 45000.0,
            "stage": "Proposal"
        }
    }
    db.execute(
        """
        INSERT INTO pending_updates (source_transcript_id, target_table, target_id, proposed_changes, status)
        VALUES (?, 'deals', ?, ?, 'pending')
        """,
        ("normal_sales_call.txt", d1, json.dumps(proposed_changes_1))
    )

    proposed_changes_2 = {
        "stage": "Proposal",
        "evidence": "Evaluating HubSpot, but open to alternatives for $30,000 budget.",
        "confidence_score": 0.80,
        "details": {
            "amount": 30000.0,
            "stage": "Proposal"
        }
    }
    db.execute(
        """
        INSERT INTO pending_updates (source_transcript_id, target_table, target_id, proposed_changes, status)
        VALUES (?, 'deals', ?, ?, 'pending')
        """,
        ("competitor_mentioned.txt", d2, json.dumps(proposed_changes_2))
    )

    print("SQLite database successfully populated with clean demo data.")

if __name__ == "__main__":
    populate()
