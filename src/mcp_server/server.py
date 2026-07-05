import os
import json
from mcp.server.fastmcp import FastMCP
from src.database.db_helper import DatabaseHelper

# Initialize the FastMCP server with a descriptive name.
mcp = FastMCP("CRM Meeting Assistant Server")

# Resolve database and schema paths relative to this file
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DB_PATH = os.path.join(BASE_DIR, "crm_assistant.db")
SCHEMA_PATH = os.path.join(BASE_DIR, "src", "database", "schema.sql")

db = DatabaseHelper(DB_PATH)

# Initialize database tables if the database file does not exist
if not os.path.exists(DB_PATH):
    db.initialize_database(SCHEMA_PATH)

@mcp.tool()
def get_contact(name: str) -> str:
    """
    Retrieve contact details by searching for their name (first name, last name, or full name).
    
    Args:
        name: The name (or part of the name) of the contact to look up.
        
    Returns:
        A JSON string containing a list of matching contacts.
    """
    query = """
        SELECT id, first_name, last_name, email, phone, company, job_title, created_at, updated_at
        FROM contacts
        WHERE first_name LIKE ? 
           OR last_name LIKE ? 
           OR (first_name || ' ' || last_name) LIKE ?
    """
    pattern = f"%{name}%"
    try:
        results = db.fetch_all(query, (pattern, pattern, pattern))
        return json.dumps(results, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})

@mcp.tool()
def get_deal_stage_options() -> list[str]:
    """
    Retrieve the allowed pipeline stages for deals in the CRM.
    
    Returns:
        A list of valid deal stage names.
    """
    return [
        "Prospecting",
        "Qualified",
        "Proposal",
        "Negotiation",
        "Closed Won",
        "Closed Lost"
    ]


if __name__ == "__main__":
    mcp.run()


