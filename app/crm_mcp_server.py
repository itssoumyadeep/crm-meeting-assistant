#!/usr/bin/env python3
# ruff: noqa
"""
Mock CRM MCP Server

A stdio-based MCP server that represents a mock CRM system.
Exposes tools:
  - get_crm_contacts()           → list all contacts
  - get_crm_deals()              → list all deals
  - update_deal_stage()          → move a deal to a new stage
  - add_action_items()           → attach action items to a deal
  - add_meeting_summary()        → attach a meeting summary note to a deal
  - get_deal_audit_trail()       → retrieve full audit trail for a deal
  - approve_crm_update()         → record a human-approved update

All state is in-memory (reset on server restart) — perfect for a demo.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types as mcp_types

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("crm-mcp-server")

# ---------------------------------------------------------------------------
# In-memory CRM store
# ---------------------------------------------------------------------------

CONTACTS = [
    {"id": "c001", "name": "Sarah Chen", "title": "VP of Engineering", "company": "Acme Corp", "email": "s.chen@acme.com"},
    {"id": "c002", "name": "Marcus Thompson", "title": "CTO", "company": "Acme Corp", "email": "m.thompson@acme.com"},
    {"id": "c003", "name": "Priya Sharma", "title": "Head of Procurement", "company": "GlobalTech Ltd", "email": "p.sharma@globaltech.com"},
]

DEALS = [
    {
        "id": "d001",
        "name": "Acme Corp Enterprise Deal",
        "company": "Acme Corp",
        "contact_ids": ["c001", "c002"],
        "stage": "Discovery",
        "value": 120000,
        "currency": "USD",
        "owner": "Alex Rivera",
        "created_at": "2026-06-01T10:00:00Z",
        "updated_at": "2026-06-20T14:30:00Z",
        "summary": "",
        "action_items": [],
        "notes": [],
    },
    {
        "id": "d002",
        "name": "GlobalTech Platform Expansion",
        "company": "GlobalTech Ltd",
        "contact_ids": ["c003"],
        "stage": "Qualified",
        "value": 85000,
        "currency": "USD",
        "owner": "Alex Rivera",
        "created_at": "2026-06-10T09:00:00Z",
        "updated_at": "2026-06-25T11:15:00Z",
        "summary": "",
        "action_items": [],
        "notes": [],
    },
]

# Audit trail — every approved write is logged here
AUDIT_TRAIL: list[dict] = []


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _find_deal(deal_id: str) -> dict | None:
    for d in DEALS:
        if d["id"] == deal_id:
            return d
    return None


def _audit(action: str, deal_id: str, approver: str, payload: dict, edit_note: str = "") -> dict:
    entry = {
        "id": f"audit_{len(AUDIT_TRAIL) + 1:04d}",
        "timestamp": _now_iso(),
        "action": action,
        "deal_id": deal_id,
        "approver": approver,
        "payload": payload,
        "edit_note": edit_note,
    }
    AUDIT_TRAIL.append(entry)
    return entry


# ---------------------------------------------------------------------------
# MCP Server definition
# ---------------------------------------------------------------------------

server = Server("crm-mcp-server")


@server.list_tools()
async def list_tools() -> list[mcp_types.Tool]:
    return [
        mcp_types.Tool(
            name="get_crm_contacts",
            description="Return all contacts in the mock CRM.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        mcp_types.Tool(
            name="get_crm_deals",
            description="Return all deals in the mock CRM.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        mcp_types.Tool(
            name="update_deal_stage",
            description=(
                "Move a deal to a new CRM pipeline stage. "
                "ONLY call this after human approval."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "deal_id": {"type": "string", "description": "The deal ID to update."},
                    "new_stage": {"type": "string", "description": "The new pipeline stage name."},
                    "approver": {"type": "string", "description": "Name of the human who approved this change."},
                    "edit_note": {"type": "string", "description": "Optional note from the reviewer."},
                },
                "required": ["deal_id", "new_stage", "approver"],
            },
        ),
        mcp_types.Tool(
            name="add_action_items",
            description=(
                "Attach approved action items to a deal. "
                "ONLY call this after human approval."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "deal_id": {"type": "string"},
                    "action_items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "item": {"type": "string"},
                                "owner": {"type": "string"},
                                "due": {"type": "string"},
                            },
                        },
                    },
                    "approver": {"type": "string"},
                    "edit_note": {"type": "string"},
                },
                "required": ["deal_id", "action_items", "approver"],
            },
        ),
        mcp_types.Tool(
            name="add_meeting_summary",
            description=(
                "Attach an approved meeting summary note to a deal. "
                "ONLY call this after human approval."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "deal_id": {"type": "string"},
                    "summary": {"type": "string"},
                    "approver": {"type": "string"},
                    "edit_note": {"type": "string"},
                },
                "required": ["deal_id", "summary", "approver"],
            },
        ),
        mcp_types.Tool(
            name="get_deal_audit_trail",
            description="Retrieve the full audit trail for a specific deal.",
            inputSchema={
                "type": "object",
                "properties": {
                    "deal_id": {"type": "string", "description": "The deal ID to query. Pass 'all' to get everything."},
                },
                "required": ["deal_id"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[mcp_types.TextContent]:
    try:
        result = await _dispatch(name, arguments)
        return [mcp_types.TextContent(type="text", text=json.dumps(result, indent=2))]
    except Exception as e:
        logger.exception("Tool error: %s", name)
        error_payload = {"error": str(e), "tool": name}
        return [mcp_types.TextContent(type="text", text=json.dumps(error_payload))]


async def _dispatch(name: str, args: dict) -> dict:
    if name == "get_crm_contacts":
        return {"status": "ok", "contacts": CONTACTS}

    elif name == "get_crm_deals":
        return {"status": "ok", "deals": DEALS}

    elif name == "update_deal_stage":
        deal_id = args["deal_id"]
        new_stage = args["new_stage"]
        approver = args.get("approver", "unknown")
        edit_note = args.get("edit_note", "")

        deal = _find_deal(deal_id)
        if not deal:
            return {"status": "error", "message": f"Deal {deal_id!r} not found"}

        old_stage = deal["stage"]
        deal["stage"] = new_stage
        deal["updated_at"] = _now_iso()

        audit_entry = _audit(
            action="update_deal_stage",
            deal_id=deal_id,
            approver=approver,
            payload={"old_stage": old_stage, "new_stage": new_stage},
            edit_note=edit_note,
        )
        return {"status": "ok", "deal_id": deal_id, "old_stage": old_stage, "new_stage": new_stage, "audit": audit_entry}

    elif name == "add_action_items":
        deal_id = args["deal_id"]
        items = args["action_items"]
        approver = args.get("approver", "unknown")
        edit_note = args.get("edit_note", "")

        deal = _find_deal(deal_id)
        if not deal:
            return {"status": "error", "message": f"Deal {deal_id!r} not found"}

        timestamped = [{"timestamp": _now_iso(), **item} for item in items]
        deal["action_items"].extend(timestamped)
        deal["updated_at"] = _now_iso()

        audit_entry = _audit(
            action="add_action_items",
            deal_id=deal_id,
            approver=approver,
            payload={"items_added": timestamped},
            edit_note=edit_note,
        )
        return {"status": "ok", "deal_id": deal_id, "items_added": len(timestamped), "audit": audit_entry}

    elif name == "add_meeting_summary":
        deal_id = args["deal_id"]
        summary = args["summary"]
        approver = args.get("approver", "unknown")
        edit_note = args.get("edit_note", "")

        deal = _find_deal(deal_id)
        if not deal:
            return {"status": "error", "message": f"Deal {deal_id!r} not found"}

        deal["summary"] = summary
        note_entry = {"timestamp": _now_iso(), "text": summary, "author": approver}
        deal["notes"].append(note_entry)
        deal["updated_at"] = _now_iso()

        audit_entry = _audit(
            action="add_meeting_summary",
            deal_id=deal_id,
            approver=approver,
            payload={"summary": summary},
            edit_note=edit_note,
        )
        return {"status": "ok", "deal_id": deal_id, "audit": audit_entry}

    elif name == "get_deal_audit_trail":
        deal_id = args["deal_id"]
        if deal_id == "all":
            return {"status": "ok", "audit_trail": AUDIT_TRAIL}
        filtered = [e for e in AUDIT_TRAIL if e["deal_id"] == deal_id]
        return {"status": "ok", "deal_id": deal_id, "audit_trail": filtered}

    else:
        return {"status": "error", "message": f"Unknown tool: {name!r}"}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
