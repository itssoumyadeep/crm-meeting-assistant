import os
import sqlite3
from typing import List, Dict, Any, Optional, Union

class DatabaseHelper:
    """
    A helper class for managing SQLite database connections and basic query executions.
    """
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._connection: Optional[sqlite3.Connection] = None

    def open(self) -> sqlite3.Connection:
        """Opens a connection to the SQLite database."""
        if not self._connection:
            self._connection = sqlite3.connect(self.db_path)
            # Enable foreign key support in SQLite
            self._connection.execute("PRAGMA foreign_keys = ON;")
            # Return rows as dict-like objects
            self._connection.row_factory = sqlite3.Row
        return self._connection

    def close(self) -> None:
        """Closes the current database connection."""
        if self._connection:
            self._connection.close()
            self._connection = None

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def initialize_database(self, schema_path: str) -> None:
        """
        Initializes the database by executing the SQL statements inside the schema file.
        """
        if not os.path.exists(schema_path):
            raise FileNotFoundError(f"Schema file not found at: {schema_path}")

        with open(schema_path, "r", encoding="utf-8") as f:
            schema_sql = f.read()

        conn = self.open()
        try:
            conn.executescript(schema_sql)
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e

    def execute(self, query: str, params: Union[tuple, dict] = ()) -> int:
        """
        Executes a write/modification query (INSERT, UPDATE, DELETE) and returns the last row ID
        or the number of affected rows.
        """
        conn = self.open()
        cursor = conn.cursor()
        try:
            cursor.execute(query, params)
            conn.commit()
            return cursor.lastrowid if cursor.lastrowid is not None else cursor.rowcount
        except Exception as e:
            conn.rollback()
            raise e

    def fetch_all(self, query: str, params: Union[tuple, dict] = ()) -> List[Dict[str, Any]]:
        """
        Executes a read query and returns all matching rows as a list of dictionaries.
        """
        conn = self.open()
        cursor = conn.cursor()
        cursor.execute(query, params)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def fetch_one(self, query: str, params: Union[tuple, dict] = ()) -> Optional[Dict[str, Any]]:
        """
        Executes a read query and returns the first matching row as a dictionary, or None.
        """
        conn = self.open()
        cursor = conn.cursor()
        cursor.execute(query, params)
        row = cursor.fetchone()
        return dict(row) if row else None
