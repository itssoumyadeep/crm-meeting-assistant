-- SQLite Schema for CRM Meeting Assistant

-- 1. Contacts Table
-- Stores information about clients, prospects, and other business contacts.
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

-- Trigger to update updated_at for contacts
CREATE TRIGGER IF NOT EXISTS update_contacts_timestamp 
AFTER UPDATE ON contacts
BEGIN
    UPDATE contacts SET updated_at = CURRENT_TIMESTAMP WHERE id = old.id;
END;

-- 2. Deals Table
-- Tracks sales opportunities associated with contacts.
CREATE TABLE IF NOT EXISTS deals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_id INTEGER,
    name TEXT NOT NULL,
    amount REAL,
    stage TEXT NOT NULL,
    status TEXT CHECK(status IN ('open', 'won', 'lost')) DEFAULT 'open',
    close_date DATE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (contact_id) REFERENCES contacts(id) ON DELETE SET NULL
);

-- Trigger to update updated_at for deals
CREATE TRIGGER IF NOT EXISTS update_deals_timestamp 
AFTER UPDATE ON deals
BEGIN
    UPDATE deals SET updated_at = CURRENT_TIMESTAMP WHERE id = old.id;
END;

-- 3. Pending Updates Table
-- Holds updates proposed by the meeting assistant (e.g., extracted from transcripts) 
-- that need human confirmation or approval before being committed to contacts/deals.
CREATE TABLE IF NOT EXISTS pending_updates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_transcript_id TEXT,
    target_table TEXT NOT NULL CHECK(target_table IN ('contacts', 'deals')),
    target_id INTEGER, -- NULL if proposing a new entry, otherwise the ID of the record to update
    proposed_changes TEXT NOT NULL, -- JSON string representing field-value pairs
    status TEXT CHECK(status IN ('pending', 'approved', 'rejected')) DEFAULT 'pending',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Trigger to update updated_at for pending_updates
CREATE TRIGGER IF NOT EXISTS update_pending_updates_timestamp 
AFTER UPDATE ON pending_updates
BEGIN
    UPDATE pending_updates SET updated_at = CURRENT_TIMESTAMP WHERE id = old.id;
END;

-- 4. Audit Logs Table
-- Tracks all system and user modifications for accountability and debugging.
CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT NOT NULL, -- e.g., 'CREATE', 'UPDATE', 'DELETE', 'APPROVE_UPDATE'
    target_table TEXT NOT NULL,
    target_id INTEGER NOT NULL,
    change_details TEXT, -- JSON showing before/after states or generic details
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for hot query paths (avoids full-table scans on every page render)
CREATE INDEX IF NOT EXISTS idx_pending_updates_status
    ON pending_updates (status);

CREATE INDEX IF NOT EXISTS idx_audit_logs_target
    ON audit_logs (target_table, target_id);

CREATE INDEX IF NOT EXISTS idx_audit_logs_timestamp
    ON audit_logs (timestamp DESC);
