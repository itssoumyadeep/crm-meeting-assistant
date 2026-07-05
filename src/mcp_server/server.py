"""
MCP server for the CRM Meeting Assistant.

Exposes two read-only tools to LLM agents via the Model Context Protocol:

- get_contact(name)          — fuzzy name search against the contacts table
- get_deal_stage_options()   — returns the canonical allow-list of CRM stages

The allow-list is defined once in ``src.utils.config.VALID_DEAL_STAGES`` and
referenced here so the pipeline guardrail and the MCP tool always agree.
"""
import json

from mcp.server.fastmcp import FastMCP

from src.database.db_helper import DatabaseHelper
from src.utils.config import DB_PATH, MCP_SERVER_NAME, SCHEMA_PATH, VALID_DEAL_STAGES
from src.utils.logging_config import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Server initialisation
# ---------------------------------------------------------------------------
mcp = FastMCP(MCP_SERVER_NAME)

# Lazy-open; DatabaseHelper will create the file if it doesn't exist
db = DatabaseHelper(DB_PATH)

# Ensure schema is applied when the server starts cold
if not DB_PATH.exists():
    logger.info("Database not found at %s — initialising schema.", DB_PATH)
    db.initialize_database(SCHEMA_PATH)

# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def get_contact(name: str) -> str:
    """
    Search for a contact by name (first name, last name, or full name).

    A ``%name%`` LIKE pattern is applied to all three columns so partial
    matches work (e.g. "Sarah" matches "Sarah Chen").

    Args:
        name: The name (or partial name) to search for.

    Returns:
        A JSON array of matching contact objects, or a JSON error object.
    """
    query = """
        SELECT id, first_name, last_name, email, phone, company, job_title,
               created_at, updated_at
        FROM   contacts
        WHERE  first_name LIKE ?
           OR  last_name  LIKE ?
           OR  (first_name || ' ' || last_name) LIKE ?
    """
    pattern = f"%{name}%"
    try:
        results = db.fetch_all(query, (pattern, pattern, pattern))
        logger.debug("get_contact('%s') → %d result(s)", name, len(results))
        return json.dumps(results, indent=2)
    except Exception:
        logger.exception("get_contact failed for name='%s'", name)
        return json.dumps({"error": f"Failed to retrieve contact for name='{name}'"})


@mcp.tool()
def get_deal_stage_options() -> list[str]:
    """
    Return the canonical list of allowed CRM pipeline stages.

    This list is the single source of truth referenced by both the pipeline
    guardrail (``before_tool_callback``) and the MCP tool surface, so they
    always agree on valid stage values.

    Returns:
        Ordered list of valid stage name strings.
    """
    return list(VALID_DEAL_STAGES)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    mcp.run()
